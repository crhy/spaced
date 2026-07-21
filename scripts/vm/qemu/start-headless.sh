#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_file "$VM_DISK" "VM disk"
build_common_args

if [ -f "$VM_PID_FILE" ] && kill -0 "$(cat "$VM_PID_FILE")" 2>/dev/null; then
    echo "VM is already running (PID $(cat "$VM_PID_FILE"))" >&2
    exit 1
fi

qemu-system-x86_64 \
    "${QEMU_COMMON[@]}" \
    -drive "file=$VM_DISK,if=virtio,format=qcow2" \
    -boot order=c -display none -serial none \
    -daemonize -pidfile "$VM_PID_FILE"

echo "Headless VM started (PID $(cat "$VM_PID_FILE")); SSH localhost:$VM_SSH_PORT"
