#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ISO=${1:-$VM_ISO}
require_file "$ISO" "ISO"
ensure_disk
build_common_args

echo "Booting $(basename "$ISO") with GTK display and $VM_DISK"
echo "SSH forwarding: localhost:$VM_SSH_PORT"
exec qemu-system-x86_64 \
    "${QEMU_COMMON[@]}" \
    -drive "file=$VM_DISK,if=virtio,format=qcow2" \
    -cdrom "$ISO" -boot order=c,once=d,menu=on \
    "${QEMU_GTK[@]}"
