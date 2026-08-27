#!/bin/bash
set -euo pipefail

ISO=${1:-}
SSH_PORT=${SPACED_VM_SSH_PORT:-2222}
TIMEOUT=${SPACED_ISO_SMOKE_TIMEOUT:-240}
MONITOR_PORT=${SPACED_QEMU_MONITOR_PORT:-4444}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-99}
ACCEL=${SPACED_QEMU_ACCEL:-kvm}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
ARTIFACT_DIR=${SPACED_QEMU_ARTIFACT_DIR:-$PROJECT_ROOT/build/test-artifacts}
SCREENSHOT=$ARTIFACT_DIR/qemu-live.ppm

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
    echo "ISO not found: ${ISO:-<not provided>}" >&2
    exit 1
fi

RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spaced-qemu-smoke.XXXXXX")
PID_FILE=$RUN_DIR/qemu.pid

cleanup() {
    local pid=
    if [ -s "$PID_FILE" ]; then
        pid=$(<"$PID_FILE")
    fi
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -KILL "$pid" 2>/dev/null || true
    fi
    if [ -d "$RUN_DIR" ]; then
        rm -r -- "$RUN_DIR"
    fi
}
trap cleanup EXIT INT TERM

capture_screen() {
    if exec 4<>"/dev/tcp/127.0.0.1/$MONITOR_PORT" 2>/dev/null; then
        printf 'screendump %s\n' "$SCREENSHOT" >&4
        sleep 1
        exec 4<&-
        exec 4>&-
    fi
    return 0
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
    sshpass -p "$ROOT_PASSWORD" ssh \
        -p "$SSH_PORT" \
        -o ConnectTimeout=2 \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        root@127.0.0.1 \
        'pgrep -x mate-session >/dev/null && pgrep -x mate-panel >/dev/null && pgrep -x caja >/dev/null && pgrep -x compiz >/dev/null' \
        >/dev/null 2>&1
}

mkdir -p "$ARTIFACT_DIR"
command -v sshpass >/dev/null || {
    echo "sshpass is required for the graphical live-session check" >&2
    exit 1
}
case "$ACCEL" in
    kvm) QEMU_ACCEL_ARGS=(-enable-kvm -cpu host) ;;
    tcg) QEMU_ACCEL_ARGS=(-accel "tcg,thread=multi" -cpu max) ;;
    *) echo "Unsupported QEMU accelerator: $ACCEL" >&2; exit 2 ;;
esac

echo "Starting $ACCEL ISO smoke test on SSH port $SSH_PORT"
qemu-system-x86_64 \
    "${QEMU_ACCEL_ARGS[@]}" -m 4096 -smp 4 \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 \
    -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc \
    -vga std -display "vnc=127.0.0.1:$VNC_DISPLAY" -serial none \
    -monitor "tcp:127.0.0.1:$MONITOR_PORT,server=on,wait=off" \
    -cdrom "$ISO" -boot order=d \
    -daemonize -pidfile "$PID_FILE"

for ((elapsed = 0; elapsed < TIMEOUT; elapsed += 5)); do
    if ssh_is_ready 2>/dev/null && desktop_is_ready; then
        # SSH starts before LightDM and MATE have finished painting the desktop.
        sleep 10
        capture_screen
        echo "$ACCEL smoke test passed: live SSH and MATE became ready after ${elapsed}s"
        echo "Screenshot: $SCREENSHOT"
        exit 0
    fi
    if [ -s "$PID_FILE" ] && ! kill -0 "$(<"$PID_FILE")" 2>/dev/null; then
        echo "$ACCEL VM exited before the live system became ready" >&2
        exit 1
    fi
    echo "Waiting for the $ACCEL live system (${elapsed}s/${TIMEOUT}s)"
    sleep 5
done

capture_screen
echo "$ACCEL live SSH and MATE did not become ready within ${TIMEOUT}s" >&2
echo "Last screenshot, if available: $SCREENSHOT" >&2
exit 1
