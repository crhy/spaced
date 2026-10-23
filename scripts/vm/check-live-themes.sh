#!/bin/bash
# Run only in a disposable live VM, after live-desktop-probe.py has passed.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
port=${1:?SSH port required}
output=${2:?Artifact directory required}
mkdir -p "$output"
export SSHPASS=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
options=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
status=0
sshpass -e ssh "${options[@]}" -p "$port" root@127.0.0.1 \
    'python3 -' < "$ROOT/scripts/vm/live-theme-probe.py" || status=$?
sshpass -e scp "${options[@]}" -P "$port" -r \
    root@127.0.0.1:/tmp/spaced-theme-review/. "$output/"
exit "$status"
