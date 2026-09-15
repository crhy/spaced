#!/bin/bash
# VirtualBox live-ISO smoke test.
#
# Graphics profiles (issue #218):
#   vboxsvga (default) - forces --graphicscontroller vboxsvga
#       --accelerate-3d off. Linux 7.1 rejects VirtualBox's default VMSVGA
#       adapter, so this keeps the Compiz desktop usable in the test.
#   default - passes neither --graphicscontroller nor --accelerate-3d, so
#       VirtualBox's own defaults for the ostype apply, as real users get
#       (VirtualBox 7.2.16 picks VBoxVGA for Debian_64). The controller VirtualBox chose is
#       recorded in the run log and the runtime JSON report.
#
# Exit codes:
#   0 - live SSH reachable, desktop usable (MATE/Compiz probe passed),
#       installer launch check passed.
#   3 - NO_WINDOW_MANAGER: the live session was reached (SSH up, mate-session
#       running) but Compiz cannot start. Diagnosed via the
#       spaced-window-manager logger message, the absence of a compiz process
#       for the live user, and `wmctrl -m` showing no window manager owns the
#       screen. This is how a VM whose graphics cannot run Compiz fails
#       (issue #218).
#   1 - any other failure (VM died, SSH/desktop never ready, blank captures,
#       installer launch check failed).
#   2 - usage error (bad arguments or numeric settings).
set -euo pipefail

GRAPHICS=${SPACED_VBOX_GRAPHICS:-vboxsvga}
ISO=""
NO_WM_EXIT=3
INSTALLER_TIMEOUT=90

usage() {
    cat <<'USAGE'
Usage: smoke-iso.sh [--graphics default|vboxsvga] <iso>
   or: smoke-iso.sh <iso>  (graphics profile from SPACED_VBOX_GRAPHICS,
                            default vboxsvga)
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --graphics)
            GRAPHICS=${2:-}
            shift 2 || { echo "--graphics needs a value" >&2; exit 2; }
            ;;
        --graphics=*)
            GRAPHICS=${1#--graphics=}
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [ -n "$ISO" ]; then
                echo "Only one ISO argument is accepted" >&2
                exit 2
            fi
            ISO=$1
            shift
            ;;
    esac
done
if [ $# -gt 0 ]; then
    for arg in "$@"; do
        if [ -n "$ISO" ]; then
            echo "Only one ISO argument is accepted" >&2
            exit 2
        fi
        ISO=$arg
    done
fi

SSH_PORT=${SPACED_VBOX_SSH_PORT:-2223}
TIMEOUT=${SPACED_ISO_SMOKE_TIMEOUT:-240}
FIRMWARE=${SPACED_VBOX_FIRMWARE:-bios}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
ARTIFACT_DIR=${SPACED_VBOX_ARTIFACT_DIR:-$PROJECT_ROOT/build/test-artifacts}
EXPECTED_VERSION=${SPACED_EXPECTED_VERSION:-$(cat "$PROJECT_ROOT/VERSION")}
RAM=${SPACED_VBOX_RAM:-2048}
CPUS=${SPACED_VBOX_CPUS:-2}

if [ "$GRAPHICS" != vboxsvga ] && [ "$GRAPHICS" != default ]; then
    echo "Graphics profile must be 'default' or 'vboxsvga' (got: ${GRAPHICS:-<empty>})" >&2
    exit 2
fi
if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
    echo "ISO not found: ${ISO:-<not provided>}" >&2
    usage >&2
    exit 1
fi
if [ "$FIRMWARE" != bios ] && [ "$FIRMWARE" != efi ]; then
    echo "SPACED_VBOX_FIRMWARE must be 'bios' or 'efi'" >&2
    exit 1
fi

for value in "$SSH_PORT" "$TIMEOUT" "$RAM" "$CPUS"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in VBoxManage sshpass ssh python3 sha256sum; do
    command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done
ISO_SHA256=$(sha256sum "$ISO" | cut -d' ' -f1)
mkdir -p "$ARTIFACT_DIR"
ARTIFACT_DIR=$(cd "$ARTIFACT_DIR" && pwd)
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spaced-vbox-smoke.XXXXXX")
VM_NAME="spaced-iso-smoke-$FIRMWARE-$GRAPHICS-$$"
SCREENSHOT=$ARTIFACT_DIR/virtualbox-$FIRMWARE-$GRAPHICS-live.png
INSTALLER_SCREENSHOT=$ARTIFACT_DIR/virtualbox-$FIRMWARE-$GRAPHICS-calamares.png
RUNTIME=$ARTIFACT_DIR/virtualbox-$FIRMWARE-$GRAPHICS-runtime.json
GUEST_LOG=$ARTIFACT_DIR/virtualbox-$FIRMWARE-$GRAPHICS-guest.log
WM_DIAGNOSIS=$ARTIFACT_DIR/virtualbox-$FIRMWARE-$GRAPHICS-no-wm.txt
EFFECTIVE_GRAPHICS_CONTROLLER=""
INSTALLER_RESULT="not-run"
INSTALLER_DETAIL=""
REGISTERED=false

cleanup() {
    if [ "$REGISTERED" = true ] && VBoxManage showvminfo "$VM_NAME" --machinereadable >/dev/null 2>&1; then
        if VBoxManage showvminfo "$VM_NAME" --machinereadable 2>/dev/null | grep -q '^VMState="running"'; then
            VBoxManage controlvm "$VM_NAME" poweroff >/dev/null 2>&1 || true
        fi
        VBoxManage unregistervm "$VM_NAME" --delete >/dev/null 2>&1 || true
    fi
    if [ -d "$RUN_DIR" ]; then
        rm -r -- "$RUN_DIR"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ssh_root() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile="$RUN_DIR/known_hosts" root@127.0.0.1 "$@"
}

ssh_is_ready() {
    local banner=
    if ! exec 3<>"/dev/tcp/127.0.0.1/$SSH_PORT"; then
        return 1
    fi
    IFS= read -r -t 2 banner <&3 || true
    exec 3<&-
    exec 3>&-
    [[ "$banner" == SSH-* ]]
}

desktop_is_ready() {
    local status=0 probe_command
    printf -v probe_command 'python3 - %q %q %q' '' '' "$EXPECTED_VERSION"
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=3 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile="$RUN_DIR/known_hosts" root@127.0.0.1 \
        "$probe_command" > "$RUNTIME.tmp" 2>> "$GUEST_LOG" \
        < "$PROJECT_ROOT/scripts/vm/live-desktop-probe.py" || status=$?
    if [ -s "$RUNTIME.tmp" ]; then mv "$RUNTIME.tmp" "$RUNTIME"; fi
    return "$status"
}

capture_screenshot_to() {
    local target=$1 size=0
    for _ in {1..8}; do
        VBoxManage controlvm "$VM_NAME" screenshotpng "$target" >/dev/null
        size=$(stat -c %s "$target" 2>/dev/null || printf 0)
        # A black 1024x768 VirtualBox frame compresses to only a few KiB. The
        # detailed Spaced wallpaper is consistently much larger than 32 KiB.
        if [ "$size" -ge 32768 ]; then
            return 0
        fi
        sleep 5
    done
    return 1
}

capture_desktop() {
    capture_screenshot_to "$SCREENSHOT"
}

# Query the guest for the three no-window-manager signals described in the
# header: the spaced-window-manager logger message, a compiz process owned by
# the live user, and whether `wmctrl -m` sees a window manager. Prints a short
# summary to stdout and returns 0 only when the desktop session is up
# (mate-session runs for user `user`) yet no window manager is active.
no_wm_confirmed() {
    local probe_output
    probe_output=$(ssh_root bash -s 2>>"$GUEST_LOG" <<'REMOTE' || true
set -u
mate_pid=$(pgrep -u user -x mate-session 2>/dev/null | head -n 1 || true)
compiz_pids=$(pgrep -u user -x compiz 2>/dev/null || true)
echo "mate_session_pid=${mate_pid:-none}"
if [ -n "$compiz_pids" ]; then
    echo "compiz_pids=$(echo "$compiz_pids" | tr '\n' ' ')"
else
    echo "compiz_pids=none"
fi
echo "--- logger ---"
if command -v journalctl >/dev/null 2>&1; then
    journalctl -t spaced-window-manager --no-pager -n 30 2>/dev/null \
        | grep -h "spaced-window-manager" || true
fi
grep -h "spaced-window-manager" /var/log/syslog /var/log/messages /var/log/user.log 2>/dev/null \
    | tail -n 30 || true
echo "--- wmctrl ---"
if [ -n "$mate_pid" ] && [ -r "/proc/$mate_pid/environ" ]; then
    display=$(tr '\0' '\n' < "/proc/$mate_pid/environ" 2>/dev/null | sed -n 's/^DISPLAY=//p' | head -n 1)
    xauth=$(tr '\0' '\n' < "/proc/$mate_pid/environ" 2>/dev/null | sed -n 's/^XAUTHORITY=//p' | head -n 1)
    : "${display:=:0}"
    : "${xauth:=/home/user/.Xauthority}"
    if command -v runuser >/dev/null 2>&1; then
        runuser -u user -- env DISPLAY="$display" XAUTHORITY="$xauth" wmctrl -m 2>&1 || echo "wmctrl_exit=$?"
    else
        su -s /bin/sh user -c "DISPLAY='$display' XAUTHORITY='$xauth' wmctrl -m" 2>&1 || echo "wmctrl_exit=$?"
    fi
else
    echo "no live session environ to query wmctrl with"
fi
REMOTE
)
    printf '%s\n' "$probe_output" >> "$WM_DIAGNOSIS"
    [ -n "$probe_output" ] || return 1
    grep -q '^mate_session_pid=[0-9]' <<<"$probe_output" || return 1
    grep -q '^compiz_pids=none' <<<"$probe_output" || return 1
    if grep -q 'without a window manager\|Compiz is unavailable\|Compiz cannot start' <<<"$probe_output"; then
        return 0
    fi
    if grep -q 'wmctrl_exit=\|Cannot get .*window manager\|no window manager' <<<"$probe_output"; then
        # compiz absent and wmctrl cannot talk to a window manager.
        if ! grep -q '^Name:' <<<"$probe_output"; then
            return 0
        fi
    fi
    return 1
}

# Launch the same installer command the desktop launcher runs, then wait up to
# $INSTALLER_TIMEOUT seconds for both a calamares process and a visible
# Calamares window. Closes Calamares cleanly afterwards. Sets INSTALLER_RESULT
# to "pass" or "fail:<reason>" and returns 0/1 accordingly. Never installs.
check_installer() {
    local elapsed=0 proc_seen="" window_seen="" launch_log="/tmp/calamares-smoke.log"
    INSTALLER_RESULT="fail:unknown"
    INSTALLER_DETAIL=""
    rm -f "$INSTALLER_SCREENSHOT"
    echo "Launching the live installer (/usr/local/bin/install-spaced-linux) as the live user"
    if ! ssh_root bash -s 2>>"$GUEST_LOG" <<REMOTE
set -u
mate_pid=\$(pgrep -u user -x mate-session 2>/dev/null | head -n 1 || true)
[ -n "\$mate_pid" ] || { echo "no live mate-session" >&2; exit 1; }
display=\$(tr '\0' '\n' < "/proc/\$mate_pid/environ" 2>/dev/null | sed -n 's/^DISPLAY=//p' | head -n 1)
xauth=\$(tr '\0' '\n' < "/proc/\$mate_pid/environ" 2>/dev/null | sed -n 's/^XAUTHORITY=//p' | head -n 1)
dbus=\$(tr '\0' '\n' < "/proc/\$mate_pid/environ" 2>/dev/null | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' | head -n 1)
: "\${display:=:0}"
: "\${xauth:=/home/user/.Xauthority}"
printf '%s %s %s' "\$display" "\$xauth" "\$dbus" > /tmp/calamares-smoke-env
setsid nohup runuser -u user -- env DISPLAY="\$display" XAUTHORITY="\$xauth" DBUS_SESSION_BUS_ADDRESS="\$dbus" /usr/local/bin/install-spaced-linux >$launch_log 2>&1 < /dev/null &
echo "installer launched"
REMOTE
    then
        INSTALLER_RESULT="fail:could not launch /usr/local/bin/install-spaced-linux over SSH"
        echo "Installer check FAILED: $INSTALLER_RESULT" >&2
        return 1
    fi
    while [ "$elapsed" -lt "$INSTALLER_TIMEOUT" ]; do
        if ssh_root "pgrep -f '^/usr/bin/calamares([[:space:]]|\$)' >/dev/null 2>&1" 2>>"$GUEST_LOG"; then
            proc_seen=yes
        fi
        if ssh_root bash -s 2>>"$GUEST_LOG" <<'REMOTE'
set -u
if [ ! -f /tmp/calamares-smoke-env ]; then exit 1; fi
read -r display xauth _dbus < /tmp/calamares-smoke-env
if command -v runuser >/dev/null 2>&1; then
    as_user() { runuser -u user -- env DISPLAY="$display" XAUTHORITY="$xauth" "$@"; }
else
    as_user() { su -s /bin/sh user -c "DISPLAY='$display' XAUTHORITY='$xauth' $*"; }
fi
# Calamares titles its window from the branding ("Spaced Linux Installer"),
# so match the X window class, which stays "calamares".
if as_user wmctrl -lx 2>/dev/null | awk '{print $3}' | grep -qi calamares; then exit 0; fi
if command -v xdotool >/dev/null 2>&1 && as_user xdotool search --class calamares >/dev/null 2>&1; then exit 0; fi
exit 1
REMOTE
        then
            window_seen=yes
        fi
        if [ -n "$proc_seen" ] && [ -n "$window_seen" ]; then
            break
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    if [ -z "$proc_seen" ]; then
        INSTALLER_RESULT="fail:no calamares process appeared within ${INSTALLER_TIMEOUT}s"
        echo "Installer check FAILED: $INSTALLER_RESULT" >&2
        return 1
    fi
    if [ -z "$window_seen" ]; then
        INSTALLER_RESULT="fail:calamares process ran but no visible Calamares window appeared within ${INSTALLER_TIMEOUT}s (wmctrl -lx / xdotool --class)"
        echo "Installer check FAILED: $INSTALLER_RESULT" >&2
        # Keep evidence of what the screen showed instead of the installer.
        capture_screenshot_to "$INSTALLER_SCREENSHOT" \
            && echo "Screen at installer failure: $INSTALLER_SCREENSHOT" >&2
    else
        if capture_screenshot_to "$INSTALLER_SCREENSHOT"; then
            echo "Installer window screenshot: $INSTALLER_SCREENSHOT"
        else
            echo "Installer window is up but its screenshot stayed blank" >&2
        fi
        INSTALLER_RESULT="pass"
        INSTALLER_DETAIL="calamares process and visible window seen after ${elapsed}s"
        echo "Installer launch check passed after ${elapsed}s (process and window visible)"
    fi
    echo "Closing Calamares without installing"
    ssh_root "pkill -f '^/usr/bin/calamares([[:space:]]|\$)' 2>/dev/null || true; for _ in 1 2 3 4 5 6; do pgrep -f '^/usr/bin/calamares([[:space:]]|\$)' >/dev/null 2>&1 || break; sleep 2; done; pkill -9 -f '^/usr/bin/calamares([[:space:]]|\$)' 2>/dev/null || true" 2>>"$GUEST_LOG" || true
    if ssh_root "pgrep -f '^/usr/bin/calamares([[:space:]]|\$)' >/dev/null 2>&1" 2>>"$GUEST_LOG"; then
        INSTALLER_DETAIL="${INSTALLER_DETAIL}; WARNING: calamares process did not exit after close request"
        echo "WARNING: calamares process did not exit after the close request" >&2
    fi
    [ "$INSTALLER_RESULT" = pass ]
}

report_no_wm() {
    echo "NO WINDOW MANAGER: live session reached but Compiz cannot start (graphics profile: $GRAPHICS)" >&2
    echo "Diagnosis (also saved in $WM_DIAGNOSIS):" >&2
    tail -n 30 "$WM_DIAGNOSIS" 2>/dev/null >&2 || true
    echo "Controller chosen by VirtualBox: ${EFFECTIVE_GRAPHICS_CONTROLLER:-unknown}" >&2
    python3 - "$RUNTIME" "$GRAPHICS" "${EFFECTIVE_GRAPHICS_CONTROLLER:-unknown}" <<'PYREPORT' 2>/dev/null || true
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    report = json.loads(path.read_text())
except (OSError, ValueError):
    report = {'desktop_ready': False, 'errors': []}
report['desktop_ready'] = False
report.setdefault('errors', []).append(
    'NO_WINDOW_MANAGER: live session reached but Compiz cannot start '
    f'(graphics profile {sys.argv[2]}, controller {sys.argv[3]}; see no-wm diagnosis file)')
report['smoke'] = {'hypervisor': 'virtualbox', 'graphics_profile': sys.argv[2],
                   'graphicscontroller': sys.argv[3], 'no_window_manager': True}
path.write_text(json.dumps(report, indent=2) + '\n')
PYREPORT
}

rm -f "$SCREENSHOT" "$INSTALLER_SCREENSHOT" "$RUNTIME" "$RUNTIME.tmp" "$WM_DIAGNOSIS"
printf '{ "desktop_ready": false, "errors": ["Guest desktop has not passed runtime checks"] }\n' > "$RUNTIME"
printf '' > "$GUEST_LOG"
printf '' > "$WM_DIAGNOSIS"
command -v sshpass >/dev/null || {
    echo "sshpass is required for the graphical live-session check" >&2
    exit 1
}
echo "Starting VirtualBox $FIRMWARE ISO smoke test on SSH port $SSH_PORT (graphics: $GRAPHICS)"
VBoxManage createvm \
    --name "$VM_NAME" \
    --platform-architecture x86 \
    --basefolder "$RUN_DIR" \
    --ostype Debian_64 \
    --register >/dev/null
REGISTERED=true

if [ "$GRAPHICS" = vboxsvga ]; then
    # Linux 7.1 rejects VirtualBox's VMSVGA vmwgfx device as an unsupported
    # hypervisor. VBoxSVGA keeps the live desktop usable without 3D support.
    VBoxManage modifyvm "$VM_NAME" \
        --memory "$RAM" --cpus "$CPUS" --vram 128 \
        --graphicscontroller vboxsvga --accelerate-3d off \
        --firmware "$FIRMWARE" --boot1 dvd --boot2 none --boot3 none --boot4 none \
        --rtc-use-utc on --audio-enabled off \
        --nic1 nat --nat-pf1 "live-ssh,tcp,127.0.0.1,$SSH_PORT,,22"
else
    # `default` profile: pass neither --graphicscontroller nor --accelerate-3d
    # so VirtualBox's own defaults for the ostype apply, exactly as real users
    # create their VMs (issue #218).
    VBoxManage modifyvm "$VM_NAME" \
        --memory "$RAM" --cpus "$CPUS" --vram 128 \
        --firmware "$FIRMWARE" --boot1 dvd --boot2 none --boot3 none --boot4 none \
        --rtc-use-utc on --audio-enabled off \
        --nic1 nat --nat-pf1 "live-ssh,tcp,127.0.0.1,$SSH_PORT,,22"
fi
EFFECTIVE_GRAPHICS_CONTROLLER=$(VBoxManage showvminfo "$VM_NAME" --machinereadable 2>/dev/null \
    | sed -n 's/^graphicscontroller="\(.*\)"$/\1/p' | head -n 1 || true)
echo "Graphics profile '$GRAPHICS': VirtualBox controller is '${EFFECTIVE_GRAPHICS_CONTROLLER:-unknown}'" | tee -a "$GUEST_LOG"
VBoxManage storagectl "$VM_NAME" --name SATA --add sata --controller IntelAhci
VBoxManage storageattach "$VM_NAME" \
    --storagectl SATA --port 0 --device 0 --type dvddrive --medium "$ISO"
VBoxManage startvm "$VM_NAME" --type headless >/dev/null

no_wm_hits=0
for ((elapsed = 0; elapsed < TIMEOUT; elapsed += 5)); do
    if ssh_is_ready 2>/dev/null && desktop_is_ready; then
        # SSH starts before LightDM and MATE have finished painting the desktop.
        sleep 5
        if ! capture_desktop; then
            echo "VirtualBox $FIRMWARE ($GRAPHICS) produced only blank desktop captures" >&2
            exit 1
        fi
        if ! check_installer; then
            echo "VirtualBox $FIRMWARE ($GRAPHICS) installer launch check failed: $INSTALLER_RESULT" >&2
            exit 1
        fi
        python3 - "$RUNTIME" "$ISO" "$ISO_SHA256" "$EXPECTED_VERSION" "$FIRMWARE" "$RAM" "$CPUS" "$SCREENSHOT" "$GRAPHICS" "$EFFECTIVE_GRAPHICS_CONTROLLER" "$INSTALLER_SCREENSHOT" "$INSTALLER_DETAIL" <<'PYREPORT'
import json
from pathlib import Path
import struct
import sys
path = Path(sys.argv[1])
report = json.loads(path.read_text())
raw = Path(sys.argv[8]).read_bytes()
if raw[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit('VirtualBox capture is not a PNG')
w, h = struct.unpack('>II', raw[16:24])
report['iso'] = {'path': sys.argv[2], 'sha256': sys.argv[3], 'expected_version': sys.argv[4]}
report['smoke'] = {'hypervisor': 'virtualbox', 'firmware': sys.argv[5], 'ram_mib': int(sys.argv[6]),
                   'cpus': int(sys.argv[7]), 'graphics_profile': sys.argv[9],
                   'graphicscontroller': sys.argv[10],
                   'installer_check': 'pass', 'installer_detail': sys.argv[12],
                   'installer_screenshot': sys.argv[11],
                   'screenshot': {'path': sys.argv[8], 'width': w, 'height': h}}
path.write_text(json.dumps(report, indent=2) + '\n')
PYREPORT
        echo "VirtualBox $FIRMWARE ($GRAPHICS, controller ${EFFECTIVE_GRAPHICS_CONTROLLER:-unknown}) smoke test passed: live SSH, MATE and installer check ready after ${elapsed}s"
        echo "Screenshot: $SCREENSHOT"
        echo "Installer screenshot: $INSTALLER_SCREENSHOT"
        exit 0
    fi
    if ! VBoxManage showvminfo "$VM_NAME" --machinereadable 2>/dev/null | grep -q '^VMState="running"'; then
        echo "VirtualBox VM stopped before the live system became ready" >&2
        exit 1
    fi
    # The `default` graphics profile is expected to reach the live session
    # without a window manager (issue #218). Detect that state early and report
    # it distinctly (exit 3) instead of timing out ambiguously. Three
    # consecutive confirmations avoid racing a merely slow Compiz startup, and
    # the vboxsvga profile keeps the full-timeout wait (its post-timeout
    # diagnosis below still reports exit 3 distinctly if Compiz failed there).
    if [ "$GRAPHICS" = default ] && ssh_is_ready 2>/dev/null && no_wm_confirmed; then
        no_wm_hits=$((no_wm_hits + 1))
        echo "Live session up without a window manager (${no_wm_hits}/3 confirmations)"
        if [ "$no_wm_hits" -ge 3 ]; then
            report_no_wm
            exit "$NO_WM_EXIT"
        fi
    else
        no_wm_hits=0
    fi
    echo "Waiting for the VirtualBox $FIRMWARE ($GRAPHICS) live system (${elapsed}s/${TIMEOUT}s)"
    sleep 5
done

VBoxManage controlvm "$VM_NAME" screenshotpng "$SCREENSHOT" >/dev/null 2>&1 || true
if ssh_is_ready 2>/dev/null && no_wm_confirmed; then
    report_no_wm
    exit "$NO_WM_EXIT"
fi
echo "VirtualBox $FIRMWARE ($GRAPHICS) live SSH and MATE did not become ready within ${TIMEOUT}s" >&2
echo "Last screenshot, if available: $SCREENSHOT" >&2
exit 1
