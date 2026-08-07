#!/bin/bash

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SPACED_VERSION=$(<"$PROJECT_ROOT/VERSION")
VM_DISK=${SPACED_VM_DISK:-$PROJECT_ROOT/build/images/spaced-linux.qcow2}
VM_DISK_SIZE=${SPACED_VM_DISK_SIZE:-25G}
VM_ISO=${SPACED_VM_ISO:-$PROJECT_ROOT/build/iso/spaced-linux-$SPACED_VERSION-amd64.iso}
VM_SSH_PORT=${SPACED_VM_SSH_PORT:-2222}
VM_PID_FILE=${SPACED_VM_PID_FILE:-/tmp/spaced-linux-vm.pid}
VM_XRES=${SPACED_VM_XRES:-1440}
VM_YRES=${SPACED_VM_YRES:-900}

require_file() {
    local path=$1 label=$2
    if [ ! -f "$path" ]; then
        echo "$label not found: $path" >&2
        exit 1
    fi
}

ensure_disk() {
    if [ ! -f "$VM_DISK" ]; then
        mkdir -p "$(dirname "$VM_DISK")"
        qemu-img create -f qcow2 "$VM_DISK" "$VM_DISK_SIZE"
    fi
}

build_common_args() {
    QEMU_COMMON=(
        -enable-kvm -cpu host -m 4096 -smp 4
        -device qemu-xhci,id=xhci
        -device usb-kbd,bus=xhci.0
        -device usb-tablet,bus=xhci.0
        -nic "user,model=virtio-net-pci,hostfwd=tcp::$VM_SSH_PORT-:22"
        # Linux expects the hardware clock in UTC. Using local time leaves the
        # guest several hours behind and breaks signed repository metadata.
        -rtc base=utc
    )
# Use QEMU's built-in standard VGA as the single GPU. Adding an explicit
    # virtio-gpu device on top of the default VGA exposes two DRM cards, which
    # makes the guest's Xorg stall and leaves LightDM on a black screen with a
    # blinking cursor. One stable card boots the desktop.
    QEMU_GTK=(
        -vga std
        -display gtk
    )
}
