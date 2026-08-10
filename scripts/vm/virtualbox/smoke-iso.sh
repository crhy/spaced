#!/bin/bash
set -euo pipefail

ISO=${1:-}
SSH_PORT=${SPACED_VBOX_SSH_PORT:-2223}
TIMEOUT=${SPACED_ISO_SMOKE_TIMEOUT:-240}
FIRMWARE=${SPACED_VBOX_FIRMWARE:-bios}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
ARTIFACT_DIR=${SPACED_VBOX_ARTIFACT_DIR:-$PROJECT_ROOT/build/test-artifacts}

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
    echo "ISO not found: ${ISO:-<not provided>}" >&2
    exit 1
fi
if [ "$FIRMWARE" != bios ] && [ "$FIRMWARE" != efi ]; then
    echo "SPACED_VBOX_FIRMWARE must be 'bios' or 'efi'" >&2
    exit 1
fi

RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spaced-vbox-smoke.XXXXXX")
VM_NAME="spaced-iso-smoke-$FIRMWARE-$$"
SCREENSHOT=$ARTIFACT_DIR/virtualbox-$FIRMWARE-live.png
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
trap cleanup EXIT INT TERM

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

mkdir -p "$ARTIFACT_DIR"
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
    --memory 4096 --cpus 4 --vram 128 \
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
