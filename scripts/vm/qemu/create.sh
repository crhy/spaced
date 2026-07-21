#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

if [ -e "$VM_DISK" ]; then
    echo "Disk already exists: $VM_DISK" >&2
    exit 1
fi

mkdir -p "$(dirname "$VM_DISK")"
qemu-img create -f qcow2 "$VM_DISK" "$VM_DISK_SIZE"
