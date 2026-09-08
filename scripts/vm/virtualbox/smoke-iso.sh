#!/bin/bash
set -euo pipefail

ISO=${1:-}
SSH_PORT=${SPACED_VBOX_SSH_PORT:-2223}
TIMEOUT=${SPACED_ISO_SMOKE_TIMEOUT:-240}
FIRMWARE=${SPACED_VBOX_FIRMWARE:-bios}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
ARTIFACT_DIR=${SPACED_VBOX_ARTIFACT_DIR:-$PROJECT_ROOT/build/test-artifacts}
EXPECTED_VERSION=${SPACED_EXPECTED_VERSION:-$(cat "$PROJECT_ROOT/VERSION")}
RAM=${SPACED_VBOX_RAM:-2048}
CPUS=${SPACED_VBOX_CPUS:-2}

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
    echo "ISO not found: ${ISO:-<not provided>}" >&2
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
VM_NAME="spaced-iso-smoke-$FIRMWARE-$$"
SCREENSHOT=$ARTIFACT_DIR/virtualbox-$FIRMWARE-live.png
RUNTIME=$ARTIFACT_DIR/virtualbox-$FIRMWARE-runtime.json
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
        "$probe_command" > "$RUNTIME.tmp" 2>> "$ARTIFACT_DIR/virtualbox-$FIRMWARE-guest.log" \
        < "$PROJECT_ROOT/scripts/vm/live-desktop-probe.py" || status=$?
    if [ -s "$RUNTIME.tmp" ]; then mv "$RUNTIME.tmp" "$RUNTIME"; fi
    return "$status"
}

capture_desktop() {
    local size=0
    for _ in {1..8}; do
        VBoxManage controlvm "$VM_NAME" screenshotpng "$SCREENSHOT" >/dev/null
        size=$(stat -c %s "$SCREENSHOT" 2>/dev/null || printf 0)
        # A black 1024x768 VirtualBox frame compresses to only a few KiB. The
        # detailed Spaced wallpaper is consistently much larger than 32 KiB.
        if [ "$size" -ge 32768 ]; then
            return 0
        fi
        sleep 5
    done
    return 1
}

rm -f "$SCREENSHOT" "$RUNTIME" "$RUNTIME.tmp"
printf '{ "desktop_ready": false, "errors": ["Guest desktop has not passed runtime checks"] }\n' > "$RUNTIME"
printf '' > "$ARTIFACT_DIR/virtualbox-$FIRMWARE-guest.log"
command -v sshpass >/dev/null || {
    echo "sshpass is required for the graphical live-session check" >&2
    exit 1
}
echo "Starting VirtualBox $FIRMWARE ISO smoke test on SSH port $SSH_PORT"
VBoxManage createvm \
    --name "$VM_NAME" \
    --platform-architecture x86 \
    --basefolder "$RUN_DIR" \
    --ostype Debian_64 \
    --register >/dev/null
REGISTERED=true

# Linux 7.1 rejects VirtualBox's VMSVGA vmwgfx device as an unsupported
# hypervisor. VBoxSVGA keeps the live desktop usable without 3D support.
VBoxManage modifyvm "$VM_NAME" \
    --memory "$RAM" --cpus "$CPUS" --vram 128 \
    --graphicscontroller vboxsvga --accelerate-3d off \
    --firmware "$FIRMWARE" --boot1 dvd --boot2 none --boot3 none --boot4 none \
    --rtc-use-utc on --audio-enabled off \
    --nic1 nat --nat-pf1 "live-ssh,tcp,127.0.0.1,$SSH_PORT,,22"
VBoxManage storagectl "$VM_NAME" --name SATA --add sata --controller IntelAhci
VBoxManage storageattach "$VM_NAME" \
    --storagectl SATA --port 0 --device 0 --type dvddrive --medium "$ISO"
VBoxManage startvm "$VM_NAME" --type headless >/dev/null

for ((elapsed = 0; elapsed < TIMEOUT; elapsed += 5)); do
    if ssh_is_ready 2>/dev/null && desktop_is_ready; then
        # SSH starts before LightDM and MATE have finished painting the desktop.
        sleep 5
        if ! capture_desktop; then
            echo "VirtualBox $FIRMWARE produced only blank desktop captures" >&2
            exit 1
        fi
        python3 - "$RUNTIME" "$ISO" "$ISO_SHA256" "$EXPECTED_VERSION" "$FIRMWARE" "$RAM" "$CPUS" "$SCREENSHOT" <<'PYREPORT'
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
                   'cpus': int(sys.argv[7]), 'screenshot': {'path': sys.argv[8], 'width': w, 'height': h}}
path.write_text(json.dumps(report, indent=2) + '\n')
PYREPORT
        echo "VirtualBox $FIRMWARE smoke test passed: live SSH and MATE became ready after ${elapsed}s"
        echo "Screenshot: $SCREENSHOT"
        exit 0
    fi
    if ! VBoxManage showvminfo "$VM_NAME" --machinereadable 2>/dev/null | grep -q '^VMState="running"'; then
        echo "VirtualBox VM stopped before the live system became ready" >&2
        exit 1
    fi
    echo "Waiting for the VirtualBox $FIRMWARE live system (${elapsed}s/${TIMEOUT}s)"
    sleep 5
done

VBoxManage controlvm "$VM_NAME" screenshotpng "$SCREENSHOT" >/dev/null 2>&1 || true
echo "VirtualBox $FIRMWARE live SSH and MATE did not become ready within ${TIMEOUT}s" >&2
echo "Last screenshot, if available: $SCREENSHOT" >&2
exit 1
