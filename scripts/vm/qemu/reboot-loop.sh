#!/bin/bash
# Spaced issue #409: on 11.26 the elogind reboot helper crashed
# (kernel: e-reboot[...]: segfault at 0 ...) and the PC sometimes stayed up.
# This test boots a live ISO headless and asks elogind for a reboot the way the
# desktop menu does, ROUNDS times, then powers the guest off.  A round passes
# only when the guest really rebooted (a different kernel boot_id) and the
# captured guest kernel log contains no "segfault" line.
#
# QEMU must NOT be started with the flag that disables guest reboots: a guest
# reboot must restart the QEMU process, exactly like a real machine rebooting.
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: reboot-loop.sh ISO [ROUNDS=5]

Boot the live ISO headless in QEMU (BIOS, -boot order=d, no disk) and run
ROUNDS elogind reboot rounds, then one power-off round.  Each round triggers
org.freedesktop.login1.Manager.Reboot from the logged-in desktop session
(falling back to "loginctl reboot" as root when polkit refuses it), captures
the guest kernel log with "dmesg --follow", and fails if that log contains
"segfault" or if the guest does not come back over SSH with a different
/proc/sys/kernel/random/boot_id.  The final round uses
org.freedesktop.login1.Manager.PowerOff and requires QEMU to exit.

QEMU is started without the flag that would disable guest reboots.

Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
Artifacts: build/vm-tests/v01/<iso-name>/
USAGE
}

ISO=${1:-}
ROUNDS=${2:-5}
if [ -z "$ISO" ]; then
    usage
    exit 2
fi
if [[ ! "$ROUNDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "ROUNDS must be a positive integer: $ROUNDS" >&2
    usage
    exit 2
fi
if [ ! -f "$ISO" ]; then
    echo "ISO not found: $ISO" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
SSH_PORT=${SPACED_VM_SSH_PORT:-2230}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-41}
RAM=${SPACED_QEMU_RAM:-4096}
CPUS=${SPACED_QEMU_CPUS:-4}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-300}
REBOOT_TIMEOUT=${SPACED_REBOOT_TIMEOUT:-240}
POWEROFF_TIMEOUT=${SPACED_POWEROFF_TIMEOUT:-120}
SESSION_TIMEOUT=${SPACED_SESSION_TIMEOUT:-120}
POLL=${SPACED_VM_POLL:-5}
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_REBOOT_LOOP_DIR:-$PROJECT_ROOT/build/vm-tests/v01/$ISO_NAME}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$RAM" "$CPUS" "$BOOT_TIMEOUT" \
             "$REBOOT_TIMEOUT" "$POWEROFF_TIMEOUT" "$SESSION_TIMEOUT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 sshpass ssh; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the reboot loop test" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "The reboot loop test needs KVM (/dev/kvm): a rebooting guest must be timed like a real PC" >&2
    exit 2
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
# Remove evidence of a previous run of this ISO (as the ISO smoke test does), so
# a round log can never be mistaken for a log of this run.
rm -f "$OUT/round-"*dmesg.txt "$OUT/round-"*trigger.log "$OUT/round-"*trigger.log.fallback \
      "$OUT/qemu.log" "$OUT/qemu-serial.log"
QEMU_PID=''
DMESG_PID=''
ELOGIND_VERSION='unknown'
FAILURES=0

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    local status=$?
    if [ -n "$DMESG_PID" ] && kill -0 "$DMESG_PID" 2>/dev/null; then
        kill "$DMESG_PID" 2>/dev/null || true
        wait "$DMESG_PID" 2>/dev/null || true
    fi
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

# The live image regenerates its SSH host keys on every boot, so a reboot loop
# must not pin them: /dev/null plus StrictHostKeyChecking=no is the only way to
# recognise the guest again after it came back from its own reboot.
guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
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

read_boot_id() {
    guest_ssh 'cat /proc/sys/kernel/random/boot_id' 2>/dev/null | tr -d '[:space:]'
}

read_elogind_version() {
    guest_ssh "dpkg-query -W -f='\${Version}' elogind" 2>/dev/null | tr -d '\n'
}

wait_for_ssh() {
    local timeout=$1 old_id=${2:-} started=$SECONDS id=
    while (( SECONDS - started < timeout )); do
        if ssh_is_ready; then
            id=$(read_boot_id || true)
            if [ -n "$id" ] && { [ -z "$old_id" ] || [ "$id" != "$old_id" ]; }; then
                return 0
            fi
        fi
        if [ -n "$QEMU_PID" ] && ! kill -0 "$QEMU_PID" 2>/dev/null; then
            return 1
        fi
        sleep "$POLL"
    done
    return 1
}

wait_for_user_session() {
    local started=$SECONDS
    while (( SECONDS - started < SESSION_TIMEOUT )); do
        if guest_ssh 'loginctl list-sessions --no-legend' 2>/dev/null | grep -q '[[:space:]]user[[:space:]]'; then
            return 0
        fi
        sleep "$POLL"
    done
    return 1
}

start_dmesg_capture() {
    local file=$1
    : > "$file"
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=5 -o ServerAliveCountMax=3 \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 \
        'dmesg --follow' > "$file" 2>&1 &
    DMESG_PID=$!
}

stop_dmesg_capture() {
    [ -n "$DMESG_PID" ] || return 0
    # The capture ssh exits by itself once the guest goes down.
    for _ in {1..15}; do
        kill -0 "$DMESG_PID" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$DMESG_PID" 2>/dev/null; then
        kill "$DMESG_PID" 2>/dev/null || true
        wait "$DMESG_PID" 2>/dev/null || true
    fi
    DMESG_PID=''
}

# Ask elogind for the power action exactly like the desktop menu does: a
# D-Bus call from the logged-in session.  When polkit refuses that caller the
# error text is recorded and the same request is retried as root with loginctl;
# $TRIGGER_METHOD says which one was used.
trigger_power_action() {
    local action=$1 log=$2 status=0
    TRIGGER_METHOD=''
    if guest_ssh "su - user -c 'DISPLAY=:0 XAUTHORITY=/home/user/.Xauthority dbus-send --system --print-reply --dest=org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager.${action} boolean:false'" \
            > "$log" 2>&1; then
        status=0
    else
        status=$?
    fi
    if grep -qi 'method return' "$log"; then
        TRIGGER_METHOD="dbus-send Manager.${action} (user session)"
        return 0
    fi
    if grep -qiE 'interactive auth|not authorized|access denied|rejected execution' "$log"; then
        echo "  desktop session call refused: $(grep -m1 -iE 'error|refus' "$log" || cat "$log")"
    else
        # The connection usually drops before ssh can show the reply, which
        # still means the call reached elogind.
        echo "  session call returned status $status without a readable reply; treating it as sent"
        TRIGGER_METHOD="dbus-send Manager.${action} (user session, no reply captured)"
        return 0
    fi
    if guest_ssh "loginctl ${action,,}" > "$log.fallback" 2>&1; then
        status=0
    else
        status=$?
    fi
    echo "  root fallback: loginctl ${action,,} (status $status)"
    TRIGGER_METHOD="loginctl ${action,,} (root fallback after polkit refusal)"
    return 0
}

report_round() {
    local label=$1 action=$2 boot_before=$3 boot_after=$4 rebooted=$5 log=$6
    # $action names the verb printed in the summary line (rebooted / powered_off).
    local segfault=no trigger="$TRIGGER_METHOD" lines
    if lines=$(grep -i 'segfault' "$log"); then
        while IFS= read -r line; do
            echo "  SEGFAULT in $log: $line"
        done <<< "$lines"
        segfault=yes
    else
        segfault=no
    fi
    if [ "$segfault" = yes ] || [ "$rebooted" = no ]; then
        FAILURES=$((FAILURES + 1))
        echo "$label: FAIL elogind=$ELOGIND_VERSION trigger=$trigger segfault=$segfault $action=$rebooted boot_id=$boot_before -> $boot_after"
    else
        echo "$label: OK elogind=$ELOGIND_VERSION trigger=$trigger segfault=$segfault $action=$rebooted boot_id=$boot_before -> $boot_after"
    fi
}

reboot_round() {
    local n=$1 log='' boot_before='' boot_after='' rebooted=no
    log="$OUT/round-$n-dmesg.txt"
    if ! wait_for_ssh "$REBOOT_TIMEOUT" ''; then
        echo "round $n: FAIL guest SSH is not reachable before the reboot"
        FAILURES=$((FAILURES + 1))
        return 1
    fi
    boot_before=$(read_boot_id || true)
    if [ -n "$boot_before" ]; then
        ELOGIND_VERSION=$(read_elogind_version || true)
        [ -n "$ELOGIND_VERSION" ] || ELOGIND_VERSION=unknown
    fi
    echo "round $n: boot_id=$boot_before elogind=$ELOGIND_VERSION"
    start_dmesg_capture "$log"
    if ! wait_for_user_session; then
        echo "  no elogind session for the live user after ${SESSION_TIMEOUT}s; the menu call is attempted anyway"
    fi
    trigger_power_action Reboot "$OUT/round-$n-trigger.log"
    stop_dmesg_capture
    if wait_for_ssh "$REBOOT_TIMEOUT" "$boot_before"; then
        boot_after=$(read_boot_id || true)
        [ -n "$boot_after" ] && rebooted=yes
    fi
    report_round "round $n" rebooted "$boot_before" "$boot_after" "$rebooted" "$log"
    [ "$rebooted" = yes ]
}

poweroff_round() {
    local n=$1 log='' boot_before='' boot_after=none rebooted=no
    log="$OUT/round-$n-poweroff-dmesg.txt"
    boot_before=$(read_boot_id || true)
    echo "round $n (power-off): boot_id=$boot_before elogind=$ELOGIND_VERSION"
    start_dmesg_capture "$log"
    trigger_power_action PowerOff "$OUT/round-$n-poweroff-trigger.log"
    local started=$SECONDS
    while (( SECONDS - started < POWEROFF_TIMEOUT )); do
        if [ -z "$QEMU_PID" ] || ! kill -0 "$QEMU_PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    stop_dmesg_capture
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        rebooted=yes
        echo "  QEMU exited $((SECONDS - started))s after the power-off request"
    else
        echo "  QEMU is still running ${POWEROFF_TIMEOUT}s after the power-off request"
    fi
    report_round "round $n (power-off)" powered_off "$boot_before" "$boot_after" "$rebooted" "$log"
    [ "$rebooted" = yes ]
}

echo "Starting reboot-loop test on $ISO ($RAM MiB, $CPUS CPUs, KVM/BIOS, SSH 127.0.0.1:$SSH_PORT)"
echo "Artifacts: $OUT"
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc -vga std -global VGA.vgamem_mb=64 \
    -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$OUT/qemu-serial.log" \
    -cdrom "$ISO" -boot order=d > "$OUT/qemu.log" 2>&1 &
QEMU_PID=$!
echo "QEMU PID $QEMU_PID (log: $OUT/qemu.log)"

if ! wait_for_ssh "$BOOT_TIMEOUT"; then
    echo "The live ISO never offered SSH on port $SSH_PORT within ${BOOT_TIMEOUT}s; see $OUT/qemu.log" >&2
    exit 2
fi
echo "Live ISO is up: boot_id=$(read_boot_id)"

for (( round = 1; round <= ROUNDS; round++ )); do
    reboot_round "$round" || true
done
poweroff_round "$((ROUNDS + 1))" || true

if [ "$FAILURES" -eq 0 ]; then
    echo "RESULT: PASS elogind=$ELOGIND_VERSION rounds=$ROUNDS"
    exit 0
fi
echo "RESULT: FAIL elogind=$ELOGIND_VERSION rounds=$ROUNDS"
exit 1
