#!/bin/bash
# Spaced Linux 11.26.1 release check: boot the released live ISO headless in
# KVM/BIOS the way scripts/vm/qemu/smoke-iso.sh does, wait for live SSH and for
# the live desktop (mate-panel, caja, compiz), then verify what is really on the
# image: the version strings, the pinned external packages, the rescue tools,
# the live password note, the smartd/apt/skel state, the xkill cursor of issue
# #414, and two screenshots for a human (xkill.png, monitor.png).
#
# Output: one PASS:/FAIL: line per check, INFO: lines for the numbers a human
# records, and a final "RESULT: PASS|FAIL passed=<n> failed=<n>".
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: live-checks.sh ISO

Boot the live ISO headless in QEMU (KVM, BIOS, -boot order=d, no disk, VNC only),
wait for live SSH and for mate-panel, caja and compiz, then run the 11.26.1 live
checks over SSH: /etc/os-release and /etc/issue versions, pinned package
versions (elogind, spaced-welcome, spaced-monitor, anacron, spaced-meta), the
rescue tools on PATH, the live password note, smartd, .gitkeep and monitors.xml
leftovers, the apt transaction guard, the xkill cursor, segfaults in dmesg, the
live SSH host key, resource numbers, and two QMP screenshots (xkill.png,
monitor.png).

Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
Artifacts: build/vm-tests/v03/<iso-name>/
USAGE
}

ISO=${1:-}
if [ -z "$ISO" ]; then
    usage
    exit 2
fi
if [ ! -f "$ISO" ]; then
    echo "ISO not found: $ISO" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
SSH_PORT=${SPACED_VM_SSH_PORT:-2231}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-43}
RAM=${SPACED_QEMU_RAM:-4096}
CPUS=${SPACED_QEMU_CPUS:-4}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-300}
DESKTOP_TIMEOUT=${SPACED_DESKTOP_TIMEOUT:-180}
POLL=${SPACED_VM_POLL:-5}
RELEASE_VERSION=$(cat "$PROJECT_ROOT/VERSION")
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_LIVE_CHECKS_DIR:-$PROJECT_ROOT/build/vm-tests/v03/$ISO_NAME}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$DESKTOP_TIMEOUT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 sshpass ssh python3 pnmtopng; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the live ISO checks" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "The live ISO checks need KVM (/dev/kvm): a live desktop must be timed like a real PC" >&2
    exit 2
fi

# Pinned external component versions, read the way scripts/iso/stage-external-artifacts.sh
# reads config/external-artifacts.conf: an exported override wins over the value
# pinned in the file.
component_version() {
    local key=$1 value=''
    value=${!key:-}
    if [ -z "$value" ]; then
        value=$(sed -n "s/^: \"\${$key:=\([^}]*\)}\"$/\1/p" \
            "$PROJECT_ROOT/config/external-artifacts.conf" | head -n 1)
    fi
    if [ -z "$value" ]; then
        echo "$key is empty in config/external-artifacts.conf" >&2
        exit 2
    fi
    printf '%s\n' "$value"
}
WELCOME_VERSION=$(component_version SPACED_WELCOME_VERSION)
MONITOR_VERSION=$(component_version SPACED_MONITOR_VERSION)

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
QMP_SOCKET="$OUT/qmp.sock"
# Remove evidence of a previous run of this ISO so an old screenshot can never be
# mistaken for one of this run.
rm -f "$OUT/qemu.log" "$OUT/qemu-serial.log" "$OUT/xkill.ppm" "$OUT/xkill.png" \
      "$OUT/monitor.ppm" "$OUT/monitor.png"

QEMU_PID=''
PASSED=0
FAILED=0
DESKTOP_READY=no
UPTIME_AT_READY=unknown

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    # QEMU is our own direct child; it is killed by that recorded PID only.
    if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$QEMU_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -KILL "$QEMU_PID" 2>/dev/null || true
    fi
    [ -z "$QEMU_PID" ] || wait "$QEMU_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The live image regenerates its SSH host keys on every boot, so a fresh live
# boot must not pin them (same as scripts/vm/qemu/smoke-iso.sh).
guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

# GUI programs of the live session: X display :0 belongs to the live user.
guest_gui() {
    guest_ssh "su - user -c 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority $1'"
}

# Start a GUI program detached from the ssh connection and print its PID, so the
# program can be stopped by that PID instead of by clicking or by name matching.
launch_gui() {
    local pid=''
    pid=$(guest_ssh "su - user -c 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority setsid $1 >/dev/null 2>&1 & echo \$!'" | tr -dc '0-9')
    printf '%s\n' "$pid"
}

ssh_is_ready() {
    local banner=
    if ! exec 3<>"/dev/tcp/127.0.0.1/$SSH_PORT" 2>/dev/null; then
        return 1
    fi
    IFS= read -r -t 2 banner <&3 || true
    exec 3<&-
    exec 3>&-
    [[ "$banner" == SSH-* ]]
}

check() {
    local name=$1 script=$2 out='' status=0 line shown=0
    # 'if out=$(...)' would lose the guest status: an if without else returns 0.
    out=$(guest_ssh 'bash -s' <<<"$script" 2>&1) && status=0 || status=$?
    if [ "$status" -eq 0 ]; then
        echo "PASS: $name"
        PASSED=$((PASSED + 1))
        return 0
    fi
    FAILED=$((FAILED + 1))
    echo "FAIL: $name (guest status $status)"
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        echo "       | $line"
        shown=$((shown + 1))
        [ "$shown" -ge 5 ] && break
    done <<< "$out"
    return 0
}

check_process() {
    local name=$1
    check "desktop: $name runs in the live session" "pgrep -x $name >/dev/null"
}

check_command() {
    local name=$1
    # shellcheck disable=SC2016  # the $... below runs in the guest, not here
    check "c: rescue tool $name is on PATH" "
if command -v $name >/dev/null; then exit 0; fi
echo '$name is not on PATH' >&2
ls -l /usr/bin/$name /usr/sbin/$name 2>&1 | grep -v 'No such file' || true
dpkg -l '*$name*' 2>/dev/null | grep '^ii' || echo 'no installed package matches $name' >&2
apt-cache policy $name 2>/dev/null | head -n 3 >&2
exit 1
"
}

pkg_version() {
    guest_ssh "dpkg-query -W -f='\${Version}' $1" 2>/dev/null | tr -d '\n'
}

check_pkg_version() {
    local name=$1 expected=$2 got=''
    got=$(pkg_version "$name")
    check "b: $name version is $expected" "
got='$got'
if [ \"\$got\" = '$expected' ]; then exit 0; fi
echo \"$name version is '\$got', expected '$expected'\" >&2
exit 1
"
}

check_pkg_installed() {
    local name=$1
    check "b: $name is installed" "
status=\$(dpkg-query -W -f='\${Status}' $name 2>&1)
case \"\$status\" in
    'install ok installed') exit 0 ;;
esac
echo \"dpkg status: \$status\" >&2
exit 1
"
}

capture_screen() {
    local file=$1
    python3 - "$QMP_SOCKET" "$file" <<'PY'
import json
import socket
import sys
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(5)
    sock.connect(sys.argv[1])
    stream = sock.makefile('rwb')
    json.loads(stream.readline())
    for request in ({'execute': 'qmp_capabilities'},
                    {'execute': 'screendump', 'arguments': {'filename': sys.argv[2]}}):
        stream.write(json.dumps(request).encode() + b'\n')
        stream.flush()
        while True:
            result = json.loads(stream.readline())
            if 'error' in result:
                raise SystemExit(str(result['error']))
            if 'return' in result:
                break
PY
}

validate_screen() {
    python3 - "$1" <<'PY'
import re
import sys
from pathlib import Path
raw = Path(sys.argv[1]).read_bytes()
header = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', raw)
if not header:
    raise SystemExit('screenshot is not an RGB PPM image')
width, height = map(int, header.groups())
pixels = raw[header.end():]
if len(pixels) != width * height * 3 or len(set(pixels)) < 8:
    raise SystemExit('screenshot is truncated or blank')
print(f'{width}x{height}')
PY
}

# Start a GUI program, screenshot the guest screen after WAIT seconds, then stop
# that program by the PID it was started with (never by a click, never by name).
screenshot_check() {
    local name=$1 command=$2 wait_seconds=$3 move_pointer=$4
    local pid='' file="$OUT/$name.ppm" size=''
    pid=$(launch_gui "$command")
    if ! [[ "$pid" =~ ^[0-9]+$ ]] || ! guest_ssh "kill -0 $pid" 2>/dev/null; then
        FAILED=$((FAILED + 1))
        echo "FAIL: j: $name started in the live session (no PID; $command)"
        return 0
    fi
    if [ "$move_pointer" = move ]; then
        # The xkill grab follows the pointer; park it at the screen centre.
        guest_gui 'xdotool mousemove 640 400' >/dev/null 2>&1 || true
    fi
    sleep "$wait_seconds"
    if capture_screen "$file" && size=$(validate_screen "$file"); then
        if pnmtopng "$file" > "$OUT/$name.png" 2>/dev/null; then
            rm -f "$file"
            echo "PASS: j: $name screenshot captured ($size) -> $OUT/$name.png"
            PASSED=$((PASSED + 1))
        else
            echo "PASS: j: $name screenshot captured ($size) -> $file"
            PASSED=$((PASSED + 1))
        fi
    else
        FAILED=$((FAILED + 1))
        echo "FAIL: j: $name screenshot captured"
    fi
    guest_ssh "kill $pid" 2>/dev/null || true
    for _ in {1..10}; do
        guest_ssh "kill -0 $pid" 2>/dev/null || break
        sleep 0.5
    done
    guest_ssh "kill -KILL $pid" 2>/dev/null || true
    return 0
}

echo "Starting live-checks on $ISO ($RAM MiB, $CPUS CPUs, KVM/BIOS, SSH 127.0.0.1:$SSH_PORT)"
echo "Artifacts: $OUT"
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc -vga std -global VGA.vgamem_mb=64 \
    -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$OUT/qemu-serial.log" \
    -qmp "unix:$QMP_SOCKET,server=on,wait=off" \
    -cdrom "$ISO" -boot order=d > "$OUT/qemu.log" 2>&1 &
QEMU_PID=$!
echo "QEMU PID $QEMU_PID (log: $OUT/qemu.log)"

started=$SECONDS
while (( SECONDS - started < BOOT_TIMEOUT )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "The VM exited early; see $OUT/qemu.log" >&2
        exit 2
    fi
    if ssh_is_ready 2>/dev/null && guest_ssh 'printf ok' >/dev/null 2>&1; then
        break
    fi
    echo "Waiting for live SSH ($((SECONDS - started))s/${BOOT_TIMEOUT}s)"
    sleep "$POLL"
done
if ! ssh_is_ready 2>/dev/null; then
    echo "The live ISO never offered SSH on port $SSH_PORT within ${BOOT_TIMEOUT}s; see $OUT/qemu.log" >&2
    exit 2
fi
echo "Live ISO is up after $((SECONDS - started))s"

started=$SECONDS
DESKTOP_WAIT=no
while (( SECONDS - started < DESKTOP_TIMEOUT )); do
    if guest_ssh 'pgrep -x mate-panel >/dev/null && pgrep -x caja >/dev/null && pgrep -x compiz >/dev/null' >/dev/null 2>&1; then
        DESKTOP_WAIT=yes
        break
    fi
    echo "Waiting for the live desktop ($((SECONDS - started))s/${DESKTOP_TIMEOUT}s)"
    sleep "$POLL"
done
UPTIME_AT_READY=$(guest_ssh 'cut -d. -f1 /proc/uptime' 2>/dev/null || echo unknown)
DESKTOP_READY=$DESKTOP_WAIT
for process in mate-panel caja compiz; do
    check_process "$process"
done
echo "INFO: desktop_ready_seconds=$UPTIME_AT_READY (uptime when mate-panel, caja and compiz ran)"

# a. release version on the image
check "a: /etc/os-release has VERSION=\"$RELEASE_VERSION\"" \
      "grep -qxF 'VERSION=\"$RELEASE_VERSION\"' /etc/os-release"
check "a: /etc/issue mentions $RELEASE_VERSION" \
      "grep -qF -- '$RELEASE_VERSION' /etc/issue"

# b. package versions, including the independently released components
check 'b: elogind version ends with +spaced'"$RELEASE_VERSION" "
got=\$(dpkg-query -W -f='\${Version}' elogind)
case \"\$got\" in
    *+spaced$RELEASE_VERSION) exit 0 ;;
esac
echo \"elogind version is '\$got', expected a +spaced$RELEASE_VERSION suffix\" >&2
exit 1
"
check_pkg_version spaced-welcome "$WELCOME_VERSION"
check_pkg_version spaced-monitor "$MONITOR_VERSION"
check_pkg_installed anacron
check_pkg_installed spaced-meta

# c. rescue tools a user needs on a live stick
for tool in gparted testdisk photorec ddrescue smartctl parted cryptsetup lvm \
            ntfs-3g mkfs.exfat efibootmgr rsync; do
    check_command "$tool"
done

# d. the live password note and the smartd daemon policy
# shellcheck disable=SC2016  # the path below is read in the guest, not here
check 'd: /home/user/Desktop/Live session passwords.txt exists and mentions spaced' '
test -f "/home/user/Desktop/Live session passwords.txt"
grep -q spaced "/home/user/Desktop/Live session passwords.txt"
'
check 'd: smartd is not running in the live session' '! pgrep -x smartd'

# e. leftovers that must never ship
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'e: no .gitkeep under /home/user' '
found=$(find /home/user -name .gitkeep -print)
test -z "$found" || { echo "$found" >&2; exit 1; }
'
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'e: no .gitkeep under /etc/skel' '
found=$(find /etc/skel -name .gitkeep -print)
test -z "$found" || { echo "$found" >&2; exit 1; }
'
check 'e: /etc/skel/.config/mate/monitors.xml does not exist' \
      '! test -e /etc/skel/.config/mate/monitors.xml'

# f. apt/dpkg state of the released image
check 'f: /etc/apt/apt.conf.d/60spaced-transaction-guard exists' \
      'test -f /etc/apt/apt.conf.d/60spaced-transaction-guard'
check 'f: apt-get check exits 0' 'apt-get check'
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'f: dpkg --audit prints nothing' '
out=$(dpkg --audit)
test -z "$out" || { echo "$out" >&2; exit 1; }
'

# g. the xkill cursor of issue #414
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'g: an Xcursor file named pirate exists under /usr/share/icons' '
found=$(find /usr/share/icons -name pirate -print -quit)
if [ -z "$found" ]; then
    echo "no pirate cursor under /usr/share/icons" >&2
    exit 1
fi
'

# h. no segfault in this boot, and live SSH really had a host key
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'h: dmesg has no segfault line' '
count=$(dmesg | grep -ci segfault || true)
test "${count:-0}" -eq 0 || { dmesg | grep -i segfault >&2; exit 1; }
'
check 'h: /etc/ssh/ssh_host_ed25519_key exists' 'test -f /etc/ssh/ssh_host_ed25519_key'

# i. numbers a human records (never pass/fail)
echo "INFO: memory_used_mib=$(guest_ssh 'free -m' 2>/dev/null | awk '/^Mem:/{print $3}')"
echo "INFO: process_count=$(guest_ssh 'ps -e --no-headers | wc -l' 2>/dev/null | tr -d '[:space:]')"
guest_ssh 'ps -eo rss=,pid=,comm= --sort=-rss | head -n 8' 2>/dev/null |
    awk '{ rss = $1; pid = $2; $1 = ""; $2 = ""; sub(/^[ \t]+/, "");
           printf "INFO: biggest_rss: rss_kB=%s pid=%s comm=%s\n", rss, pid, $0 }'

# j. two screenshots for a human, taken with QMP screendump
if [ "$DESKTOP_READY" = yes ]; then
    screenshot_check xkill xkill 2 move
    screenshot_check monitor spaced-monitor 8 stay
else
    FAILED=$((FAILED + 2))
    echo 'FAIL: j: xkill screenshot captured (no live desktop to screenshot)'
    echo 'FAIL: j: monitor screenshot captured (no live desktop to screenshot)'
fi

echo "Artifacts: $OUT"
if [ "$FAILED" -eq 0 ]; then
    echo "RESULT: PASS passed=$PASSED failed=$FAILED"
    exit 0
fi
echo "RESULT: FAIL passed=$PASSED failed=$FAILED"
exit 1
