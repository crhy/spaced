#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

if [ ! -f "$VM_PID_FILE" ]; then
    echo "No headless VM PID file found"
    exit 0
fi

pid=$(cat "$VM_PID_FILE")
if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "Stopped VM PID $pid"
fi
rm -f "$VM_PID_FILE"
