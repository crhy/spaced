#!/bin/bash
set -euo pipefail

ISO=${1:-}
SSH_PORT=${SPACED_VM_SSH_PORT:-2222}
TIMEOUT=${SPACED_ISO_SMOKE_TIMEOUT:-240}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-99}
ACCEL=${SPACED_QEMU_ACCEL:-kvm}
FIRMWARE=${SPACED_QEMU_FIRMWARE:-bios}
RAM=${SPACED_QEMU_RAM:-2048}
CPUS=${SPACED_QEMU_CPUS:-2}
XRES=${SPACED_QEMU_XRES:-}
YRES=${SPACED_QEMU_YRES:-}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
ARTIFACT_DIR=${SPACED_QEMU_ARTIFACT_DIR:-$PROJECT_ROOT/build/test-artifacts}
EXPECTED_VERSION=${SPACED_EXPECTED_VERSION:-$(cat "$PROJECT_ROOT/VERSION")}

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
    echo "ISO not found: ${ISO:-<not provided>}" >&2
    exit 1
fi
for value in "$SSH_PORT" "$TIMEOUT" "$VNC_DISPLAY" "$RAM" "$CPUS"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
if [ -n "$XRES$YRES" ] && ! { [[ "$XRES" =~ ^[1-9][0-9]*$ ]] && [[ "$YRES" =~ ^[1-9][0-9]*$ ]]; }; then
    echo 'Set both SPACED_QEMU_XRES and SPACED_QEMU_YRES to positive pixels.' >&2
    exit 2
fi
for tool in qemu-system-x86_64 sshpass ssh python3 sha256sum; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the ISO smoke test" >&2; exit 1; }
done
ISO_SHA256=$(sha256sum "$ISO" | cut -d' ' -f1)
mkdir -p "$ARTIFACT_DIR"
ARTIFACT_DIR=$(cd "$ARTIFACT_DIR" && pwd)
SCREENSHOT="$ARTIFACT_DIR/qemu-live.ppm"
RUNTIME="$ARTIFACT_DIR/qemu-runtime.json"
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spaced-qemu-smoke.XXXXXX")
QMP_SOCKET="$RUN_DIR/qmp.sock"
QEMU_PID=''
cleanup() {
    # QEMU is our direct child, never a PID obtained from a shared file/port.
    if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$QEMU_PID" 2>/dev/null || break
            sleep 0.1
        done
        kill -KILL "$QEMU_PID" 2>/dev/null || true
    fi
    [ -z "$QEMU_PID" ] || wait "$QEMU_PID" 2>/dev/null || true
    rm -r -- "$RUN_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

capture_screen() {
    python3 - "$QMP_SOCKET" "$SCREENSHOT" <<'PY'
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
    # Query the real live user's X session rather than assuming :0/.Xauthority.
    local status=0 probe_command
    printf -v probe_command 'python3 - %q %q %q' "$XRES" "$YRES" "$EXPECTED_VERSION"
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=3 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile="$RUN_DIR/known_hosts" root@127.0.0.1 \
        "$probe_command" > "$RUNTIME.tmp" 2>> "$ARTIFACT_DIR/qemu-guest.log" < "$PROJECT_ROOT/scripts/vm/live-desktop-probe.py" || status=$?
    if [ -s "$RUNTIME.tmp" ]; then
        mv "$RUNTIME.tmp" "$RUNTIME"
    fi
    return "$status"
}

validate_screen() {
    python3 - "$SCREENSHOT" "$RUNTIME" "$ACCEL" "$FIRMWARE" "$RAM" "$CPUS" "$XRES" "$YRES" "$ISO" "$ISO_SHA256" "$EXPECTED_VERSION" <<'PY'
import json
from pathlib import Path
import re
import sys
raw = Path(sys.argv[1]).read_bytes()
header = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', raw)
if not header:
    raise SystemExit('Screenshot is not an RGB PPM image')
w, h = map(int, header.groups())
pixels = raw[header.end():]
if len(pixels) != w*h*3 or len(set(pixels)) < 8:
    raise SystemExit('Screenshot is truncated or blank')
if sys.argv[7] and (w, h) != (int(sys.argv[7]), int(sys.argv[8])):
    raise SystemExit(f'Screenshot is {w}x{h}, not the requested display size')
path = Path(sys.argv[2])
report = json.loads(path.read_text())
report['iso'] = {'path': sys.argv[9], 'sha256': sys.argv[10], 'expected_version': sys.argv[11]}
report['smoke'] = {'accelerator': sys.argv[3], 'firmware': sys.argv[4],
                   'ram_mib': int(sys.argv[5]), 'cpus': int(sys.argv[6]),
                   'screenshot': {'path': sys.argv[1], 'width': w, 'height': h, 'nonblank': True}}
path.write_text(json.dumps(report, indent=2) + '\n')
PY
}

case "$ACCEL" in
    kvm) QEMU_ACCEL_ARGS=(-enable-kvm -cpu host) ;;
    tcg) QEMU_ACCEL_ARGS=(-accel "tcg,thread=multi" -cpu max) ;;
    *) echo "Unsupported QEMU accelerator: $ACCEL" >&2; exit 2 ;;
esac
FIRMWARE_ARGS=()
case "$FIRMWARE" in
    bios) ;;
    efi|uefi)
        FIRMWARE=uefi
        code=${SPACED_OVMF_CODE:-}
        vars=${SPACED_OVMF_VARS:-}
        if [ -z "$code$vars" ]; then
            for suffix in _4M ''; do
                if [ -f "/usr/share/OVMF/OVMF_CODE${suffix}.fd" ] && [ -f "/usr/share/OVMF/OVMF_VARS${suffix}.fd" ]; then
                    code="/usr/share/OVMF/OVMF_CODE${suffix}.fd"
                    vars="/usr/share/OVMF/OVMF_VARS${suffix}.fd"
                    break
                fi
            done
        fi
        if [ ! -f "$code" ] || [ ! -f "$vars" ]; then
            echo 'UEFI requires a matching OVMF_CODE/OVMF_VARS pair (SPACED_OVMF_CODE/VARS).' >&2
            exit 2
        fi
        cp "$vars" "$RUN_DIR/OVMF_VARS.fd"
        chmod 600 "$RUN_DIR/OVMF_VARS.fd"
        FIRMWARE_ARGS=(-drive "if=pflash,format=raw,readonly=on,file=$code"
                       -drive "if=pflash,format=raw,file=$RUN_DIR/OVMF_VARS.fd")
        ;;
    *) echo "Unsupported QEMU firmware: $FIRMWARE" >&2; exit 2 ;;
esac
DISPLAY_ARGS=(-vga std -global VGA.vgamem_mb=64)
if [ -n "$XRES" ]; then
    DISPLAY_ARGS+=(-global "VGA.xres=$XRES" -global "VGA.yres=$YRES")
fi
# Remove evidence from a previous invocation before starting this VM.
rm -f "$SCREENSHOT" "$RUNTIME" "$RUNTIME.tmp"
python3 - "$RUNTIME" "$ACCEL" "$FIRMWARE" <<'PY'
import json
from pathlib import Path
import sys
Path(sys.argv[1]).write_text(json.dumps({'desktop_ready': False,
    'errors': ['Guest desktop has not passed runtime checks'],
    'accelerator': sys.argv[2], 'firmware': sys.argv[3]}, indent=2) + '\n')
PY
printf '' > "$ARTIFACT_DIR/qemu-guest.log"
echo "Starting $ACCEL/$FIRMWARE ISO smoke test (${RAM} MiB, $CPUS CPUs) on SSH port $SSH_PORT"
qemu-system-x86_64 "${QEMU_ACCEL_ARGS[@]}" -m "$RAM" -smp "$CPUS" \
    "${FIRMWARE_ARGS[@]}" -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc "${DISPLAY_ARGS[@]}" -display "vnc=127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$ARTIFACT_DIR/qemu-serial.log" \
    -qmp "unix:$QMP_SOCKET,server=on,wait=off" \
    -cdrom "$ISO" -boot order=d > "$ARTIFACT_DIR/qemu.log" 2>&1 &
QEMU_PID=$!
started=$SECONDS
while (( SECONDS - started < TIMEOUT )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "$ACCEL/$FIRMWARE VM exited early; see $ARTIFACT_DIR/qemu.log" >&2
        exit 1
    fi
    if ssh_is_ready 2>/dev/null && desktop_is_ready; then
        # Let the desktop finish painting, then recheck after the mode switch.
        sleep 3
        if desktop_is_ready && capture_screen && validate_screen; then
            echo "$ACCEL/$FIRMWARE smoke passed after $((SECONDS - started))s"
            echo "Screenshot: $SCREENSHOT"
            echo "Runtime evidence: $RUNTIME"
            exit 0
        fi
    fi
    echo "Waiting for the $ACCEL/$FIRMWARE live desktop ($((SECONDS - started))s/${TIMEOUT}s)"
    sleep 5
done
capture_screen || true
echo "$ACCEL/$FIRMWARE live desktop did not pass within ${TIMEOUT}s" >&2
echo "Evidence: $ARTIFACT_DIR" >&2
exit 1
