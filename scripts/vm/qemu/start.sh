#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_file "$VM_DISK" "VM disk"
build_common_args

echo "Booting installed Spaced Linux disk with GTK display"
echo "SSH forwarding: localhost:$VM_SSH_PORT"
exec qemu-system-x86_64 \
    "${QEMU_COMMON[@]}" \
    -drive "file=$VM_DISK,if=virtio,format=qcow2" \
    -boot order=c \
    "${QEMU_GTK[@]}"
