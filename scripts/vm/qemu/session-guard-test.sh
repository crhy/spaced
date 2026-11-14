#!/bin/bash
# g01 session guard: prove on a real live Spaced desktop that an elogind
# package restart drops the running session, and that the Spaced session guard
# (overlays/usr/lib/spaced-linux/spaced-policy-rc.d, installed as
# /usr/sbin/policy-rc.d by spaced-mate-default-settings 11.26.1-2) prevents it.
#
# Round A (the ISO exactly as shipped, no guard): wait for the live desktop,
# record the session count, the elogind PID and the /run/user/1000 entry count,
# then run the commands the elogind package scripts run on every upgrade
# (invoke-rc.d elogind stop; sleep 2; invoke-rc.d elogind start; sleep 3) and
# record the same three values. Expected: the session is gone or the runtime
# directory is emptied -> "ROUND A: bug reproduced".
#
# The VM is then rebooted (a fresh live boot), the guard is copied into the
# guest and linked to /usr/sbin/policy-rc.d, and the same commands run again as
# Round B. Required: session count unchanged and >= 1, elogind PID unchanged,
# /run/user/1000 entry count unchanged. Round B then runs a real
# "apt-get install --reinstall -y elogind" (the package's own prerm/postinst,
# needs network). If the configured archives cannot deliver that exact patched
# version, the identical .deb from build/local-packages is installed by file
# instead, which runs the same maintainer scripts; if neither is available the
# transaction is recorded and skipped. The three values are rechecked either
# way.
#
# Output: PASS:/FAIL:/INFO: lines, the ROUND A:/ROUND B: verdicts and a final
# "RESULT: PASS|FAIL passed=<n> failed=<n>".
# Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
# Artifacts: build/vm-tests/g01/
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: session-guard-test.sh ISO

Boot the live ISO (build/iso/spaced-linux-11.26.1-amd64.iso) headless in QEMU
(KVM, 4 GB, 4 CPUs, BIOS, no disk, -display none + VNC), wait for the MATE
desktop, and compare an "invoke-rc.d elogind stop/start" cycle without the
session guard (Round A) and with it installed (Round B, after a VM reboot).

Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
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
ISO=$(cd "$(dirname "$ISO")" && pwd)/${ISO##*/}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
GUARD=$PROJECT_ROOT/overlays/usr/lib/spaced-linux/spaced-policy-rc.d
SSH_PORT=${SPACED_VM_SSH_PORT:-2234}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-46}
RAM=${SPACED_QEMU_RAM:-4096}
CPUS=${SPACED_QEMU_CPUS:-4}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-420}
POLL=${SPACED_VM_POLL:-5}
REINSTALL_TIMEOUT=${SPACED_ELOGIND_REINSTALL_TIMEOUT:-900}
EXPECTED_VERSION=$(cat "$PROJECT_ROOT/VERSION")
OUT=${SPACED_SESSION_GUARD_TEST_DIR:-$PROJECT_ROOT/build/vm-tests/g01}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$POLL" \
             "$REINSTALL_TIMEOUT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
if [ "$SSH_PORT" -lt 2230 ] || [ "$SSH_PORT" -gt 2239 ]; then
    echo "The session guard test must use an SSH port in 2230-2239, not $SSH_PORT" >&2
    exit 2
fi
for tool in qemu-system-x86_64 sshpass ssh scp python3; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the session guard test" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "The session guard test needs KVM (/dev/kvm): the live desktop must boot like a real PC" >&2
    exit 2
fi
if [ ! -f "$GUARD" ]; then
    echo "The session guard script is missing: $GUARD" >&2
    exit 2
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
# Never let evidence from a previous run be mistaken for this one.
rm -f "$OUT"/*.log "$OUT"/*.txt "$OUT"/*.ppm "$OUT"/*.json
rm -rf "$OUT"/run.*

RUN_DIR=$(mktemp -d "$OUT/run.XXXXXX")
QMP_SOCKET="$RUN_DIR/qmp.sock"
QEMU_PID=''
PASSED=0
FAILED=0
# Guest programs live in files: they are reused, archived and quoted by the
# guest shell, never by this one.
STATE_FILE=$RUN_DIR/guest-state.sh
RESTART_FILE=$RUN_DIR/guest-restart.sh
IMAGE_STATE_FILE=$RUN_DIR/guest-image-state.sh
INSTALL_GUARD_FILE=$RUN_DIR/guest-install-guard.sh

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    # QEMU is our own direct child and is stopped by the PID recorded for it,
    # never by name matching.
    if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$QEMU_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -KILL "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    QEMU_PID=''
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=15 -o ServerAliveCountMax=20 \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

# Run a shell program in the guest with its stderr folded into the captured
# output, so invoke-rc.d's own denial message lands in the artifact.
guest_sh() {
    guest_ssh "bash -s 2>&1"
}

# Run a python3 program in the guest (stdin) with shell-quoted arguments.
guest_python() {
    local argument quoted=''
    for argument in "$@"; do
        printf -v argument '%q' "$argument"
        quoted+=" $argument"
    done
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "python3 -$quoted"
}

guest_scp() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e scp -P "$SSH_PORT" -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$@"
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

pass() {
    echo "PASS: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

info() {
    echo "INFO: $1"
}

capture_screen() {
    local path=$1
    python3 - "$QMP_SOCKET" "$path" <<'PY' || info "screenshot failed for $path"
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

# The three values this test is about, plus whether the runtime directory
# itself still exists.
cat > "$STATE_FILE" <<'GUEST'
session_count=$(loginctl list-sessions --no-legend 2>/dev/null | wc -l)
daemon_pid=$(pgrep -x elogind | head -n 1)
echo "sessions=$session_count"
echo "elogind_pid=${daemon_pid:-0}"
echo "runtime_dir=$([ -d /run/user/1000 ] && echo present || echo missing)"
echo "runtime_entries=$(ls -A /run/user/1000 2>/dev/null | wc -l)"
GUEST

record() {
    local round=$1 stage=$2 out
    out="$OUT/$round-$stage.txt"
    guest_sh < "$STATE_FILE" > "$out"
    capture_screen "$OUT/$round-$stage.ppm"
    info "$round/$stage: $(tr '\n' ' ' < "$out")"
}

value() {
    awk -F= -v key="$2" '$1 == key { print $2; exit }' "$1"
}

# Exactly what the elogind package's own prerm and postinst do through
# invoke-rc.d on every upgrade (dh_installinit: prerm stop, postinst restart).
cat > "$RESTART_FILE" <<'GUEST'
invoke-rc.d elogind stop
echo "stop_status=$?"
sleep 2
invoke-rc.d elogind start
echo "start_status=$?"
sleep 3
GUEST

start_vm() {
    local round=$1
    rm -f "$QMP_SOCKET"
    qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
        -device qemu-xhci,id=xhci \
        -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
        -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
        -rtc base=utc -vga std -global VGA.vgamem_mb=64 \
        -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
        -serial "file:$OUT/qemu-serial-$round.log" \
        -qmp "unix:$QMP_SOCKET,server=on,wait=off" \
        -cdrom "$ISO" -boot order=d > "$OUT/qemu-$round.log" 2>&1 &
    QEMU_PID=$!
    info "QEMU PID $QEMU_PID (round $round, log: $OUT/qemu-$round.log)"
}

# Wait for SSH and then for the real live desktop (MATE session, panel, Caja,
# Compiz and the release identity): the same probe the ISO smoke test uses.
wait_for_desktop() {
    local round=$1 started=$SECONDS status=0
    while (( SECONDS - started < BOOT_TIMEOUT )); do
        if ! kill -0 "$QEMU_PID" 2>/dev/null; then
            echo "The VM exited early; see $OUT/qemu-$round.log" >&2
            exit 2
        fi
        if ssh_is_ready 2>/dev/null; then
            status=0
            guest_python '' '' "$EXPECTED_VERSION" \
                < "$PROJECT_ROOT/scripts/vm/live-desktop-probe.py" \
                > "$OUT/desktop-$round.json" 2>> "$OUT/qemu-$round.log" || status=$?
            if [ "$status" -eq 0 ]; then
                info "live desktop ready after $((SECONDS - started))s (round $round)"
                return 0
            fi
        fi
        info "waiting for the live desktop, round $round ($((SECONDS - started))s/${BOOT_TIMEOUT}s)"
        sleep "$POLL"
    done
    echo "The live desktop never became ready in round $round within ${BOOT_TIMEOUT}s" >&2
    return 1
}

echo "g01 session guard test: $ISO"
echo "Artifacts: $OUT"
echo "Guard script under test: $GUARD"

# ---------------------------------------------------------------- Round A ---
# The ISO as shipped: no /usr/sbin/policy-rc.d, so the package scripts get
# their way and the running session is lost.
start_vm A
if ! wait_for_desktop A; then
    exit 2
fi
cat > "$IMAGE_STATE_FILE" <<'GUEST'
ls -l /usr/sbin/policy-rc.d 2>&1 || echo "no policy-rc.d in the image"
dpkg-query -W -f='${Package} ${Version}\n' elogind
echo "xorg_pid=$(pgrep -x Xorg | head -n 1)"
GUEST
guest_sh < "$IMAGE_STATE_FILE" > "$OUT/A-setup.txt"
info "image state: $(tr '\n' ' ' < "$OUT/A-setup.txt")"
record A before
guest_sh < "$RESTART_FILE" | tee "$OUT/A-stop-start.txt"
record A after

sessions_before=$(value "$OUT/A-before.txt" sessions)
sessions_after=$(value "$OUT/A-after.txt" sessions)
pid_before=$(value "$OUT/A-before.txt" elogind_pid)
pid_after=$(value "$OUT/A-after.txt" elogind_pid)
entries_before=$(value "$OUT/A-before.txt" runtime_entries)
entries_after=$(value "$OUT/A-after.txt" runtime_entries)
if [ "$sessions_after" -eq 0 ] || [ "$entries_after" -lt "$entries_before" ]; then
    echo "ROUND A: bug reproduced"
    pass "round A control: without the guard the session is lost (sessions $sessions_before -> $sessions_after, /run/user/1000 entries $entries_before -> $entries_after, elogind PID $pid_before -> $pid_after)"
else
    echo "ROUND A: bug NOT reproduced"
    fail "round A control: expected the shipped image to lose the session (sessions $sessions_before -> $sessions_after, /run/user/1000 entries $entries_before -> $entries_after, elogind PID $pid_before -> $pid_after)"
fi

# ---------------------------------------------------------------- Round B ---
# A fresh live boot, with the guard installed the way the 11.26.1-2 settings
# package installs it.
cleanup
sleep 3
start_vm B
if ! wait_for_desktop B; then
    exit 2
fi
guest_scp "$GUARD" root@127.0.0.1:/usr/lib/spaced-linux/spaced-policy-rc.d
cat > "$INSTALL_GUARD_FILE" <<'GUEST'
chmod 755 /usr/lib/spaced-linux/spaced-policy-rc.d
ln -s /usr/lib/spaced-linux/spaced-policy-rc.d /usr/sbin/policy-rc.d
ls -l /usr/sbin/policy-rc.d
sh -n /usr/sbin/policy-rc.d && echo "guard syntax ok"
/usr/sbin/policy-rc.d elogind stop
echo "guard_probe_status=$?"
GUEST
if ! guest_sh < "$INSTALL_GUARD_FILE" > "$OUT/B-setup.txt"; then
    echo "The guard could not be installed in the guest:" >&2
    cat "$OUT/B-setup.txt" >&2
    exit 1
fi
info "guard installed: $(tr '\n' ' ' < "$OUT/B-setup.txt")"
record B before
guest_sh < "$RESTART_FILE" | tee "$OUT/B-stop-start.txt"
record B after

sessions_before=$(value "$OUT/B-before.txt" sessions)
sessions_after=$(value "$OUT/B-after.txt" sessions)
pid_before=$(value "$OUT/B-before.txt" elogind_pid)
pid_after=$(value "$OUT/B-after.txt" elogind_pid)
entries_before=$(value "$OUT/B-before.txt" runtime_entries)
entries_after=$(value "$OUT/B-after.txt" runtime_entries)
if [ "$sessions_after" = "$sessions_before" ] && [ "$sessions_after" -ge 1 ] \
   && [ "$pid_after" = "$pid_before" ] && [ "$pid_after" != "0" ] \
   && [ "$entries_after" = "$entries_before" ] && [ "$entries_after" -ge 1 ]; then
    pass "round B: the guard keeps the session through an elogind stop/start (sessions $sessions_before, elogind PID $pid_before, /run/user/1000 entries $entries_before)"
else
    fail "round B: the session changed (sessions $sessions_before -> $sessions_after, elogind PID $pid_before -> $pid_after, /run/user/1000 entries $entries_before -> $entries_after)"
fi
if grep -q 'denied execution' "$OUT/B-stop-start.txt"; then
    pass 'round B: invoke-rc.d reported the policy denial instead of stopping elogind'
else
    fail "round B: invoke-rc.d never reported a policy denial; see $OUT/B-stop-start.txt"
fi
if grep -q 'start_status=[^0]' "$OUT/B-stop-start.txt"; then
    info 'the follow-up "start" reported a failure only because the guard left the daemon running: start-stop-daemon launched its own child, waited for a readiness notification that the running daemon already owns, timed out and killed that child. The running elogind PID is unchanged. The package scripts ask for "restart", which the guard denies outright.'
fi

# A real package transaction: the installed elogind's own prerm/postinst run
# against the running session. Ask APT for the installed version first; the
# live image's lists are from build time, so refresh them once before giving
# up. APT exits 0 while printing "Reinstallation of elogind is not possible, it
# cannot be downloaded" when the patched +spaced build is not in any configured
# archive, so that case is recorded as skipped rather than counted as a run.
# The identical .deb from this build tree is then installed by file, which runs
# exactly the same maintainer scripts.
transaction_ran=0
for attempt in 1 2; do
    if [ "$attempt" = 2 ]; then
        guest_ssh "timeout $REINSTALL_TIMEOUT apt-get update -o Acquire::Retries=3" \
            > "$OUT/B-apt-update.txt" 2>&1 || true
    fi
    if guest_ssh "timeout $REINSTALL_TIMEOUT env DEBIAN_FRONTEND=noninteractive apt-get install --reinstall -y elogind" \
        > "$OUT/B-reinstall-$attempt.txt" 2>&1 \
        && ! grep -qi 'not possible, it cannot be downloaded' "$OUT/B-reinstall-$attempt.txt"; then
        transaction_ran=1
        break
    fi
    info "apt-get install --reinstall elogind attempt $attempt did not run the package scripts (see $OUT/B-reinstall-$attempt.txt)"
done

if [ "$transaction_ran" -eq 0 ]; then
    installed_version=$(guest_ssh "dpkg-query -W -f='\${Version}' elogind" | tr -d '\r')
    info "configured archives cannot deliver elogind $installed_version"
    local_deb=$(find "$PROJECT_ROOT/build/local-packages" -maxdepth 1 -type f \
        -name "elogind_${installed_version}_amd64.deb" 2>/dev/null | head -n 1)
    if [ -n "$local_deb" ]; then
        info "installing the identical $local_deb from this build tree instead"
        guest_ssh 'mkdir -p /var/tmp/spaced-g01'
        guest_scp "$local_deb" root@127.0.0.1:/var/tmp/spaced-g01/
        if guest_ssh "timeout $REINSTALL_TIMEOUT env DEBIAN_FRONTEND=noninteractive apt-get install -y /var/tmp/spaced-g01/${local_deb##*/}" \
            > "$OUT/B-reinstall-local.txt" 2>&1; then
            transaction_ran=1
        else
            info "the local elogind deb could not be installed; see $OUT/B-reinstall-local.txt"
        fi
    fi
fi

if [ "$transaction_ran" -eq 0 ]; then
    info 'round B package transaction skipped: this elogind version could not be downloaded and no identical .deb exists in build/local-packages'
else
    sleep 3
    record B after-reinstall
    sessions_now=$(value "$OUT/B-after-reinstall.txt" sessions)
    pid_now=$(value "$OUT/B-after-reinstall.txt" elogind_pid)
    entries_now=$(value "$OUT/B-after-reinstall.txt" runtime_entries)
    if [ "$sessions_now" = "$sessions_before" ] && [ "$sessions_now" -ge 1 ] \
       && [ "$pid_now" = "$pid_before" ] \
       && [ "$entries_now" = "$entries_before" ]; then
        pass "round B: a real elogind package transaction left the session alone (sessions $sessions_now, elogind PID $pid_now, /run/user/1000 entries $entries_now)"
    else
        fail "round B: the real elogind transaction changed the session (sessions $sessions_before -> $sessions_now, elogind PID $pid_before -> $pid_now, /run/user/1000 entries $entries_before -> $entries_now)"
    fi
fi

cleanup
echo "RESULT: $([ "$FAILED" -eq 0 ] && echo PASS || echo FAIL) passed=$PASSED failed=$FAILED"
[ "$FAILED" -eq 0 ]
