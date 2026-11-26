#!/bin/bash
# Refuse APT publication unless the exact candidate Packages index passed the
# public-image upgrade and two-machine network-services gate.
set -euo pipefail

REPO_DIR=${1:-}
EVIDENCE=${2:-}
[ -n "$REPO_DIR" ] && [ -n "$EVIDENCE" ] || {
    echo "Usage: verify-published-upgrade-evidence.sh REPO_DIR PASS.env" >&2
    exit 2
}
[ -d "$REPO_DIR" ] || { echo "APT repository not found: $REPO_DIR" >&2; exit 2; }
[ -s "$EVIDENCE" ] || {
    echo "Refusing publication: missing published-upgrade evidence: $EVIDENCE" >&2
    exit 1
}

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
VERSION=$(cat "$PROJECT_ROOT/VERSION")
SUITE=${SPACED_APT_SUITE:-spaced}
PACKAGES=$REPO_DIR/dists/$SUITE/main/binary-amd64/Packages
[ -s "$PACKAGES" ] || { echo "Packages index not found: $PACKAGES" >&2; exit 2; }

field() {
    local key=$1
    awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); found++ }
        END { if (found != 1) exit 1 }' "$EVIDENCE"
}

EXPECTED_HASH=$(sha256sum "$PACKAGES" | awk '{print $1}')
ISO_HASH=$(field iso_sha256)
COMPLETED_AT=$(field completed_at)
BASE_VERSION=$(field base_version)
[ "$(field result)" = PASS ] || { echo "Refusing publication: gate result is not PASS" >&2; exit 1; }
[ "$(field version)" = "$VERSION" ] || { echo "Refusing publication: evidence is for another OS version" >&2; exit 1; }
[[ "$BASE_VERSION" =~ ^(1[0-2]|[1-9])\.[0-9]{2}(\.[0-9]+)?$ ]] || {
    echo "Refusing publication: invalid public base version" >&2
    exit 1
}
[ "$(field iso_name)" = "spaced-linux-$BASE_VERSION-amd64.iso" ] || {
    echo "Refusing publication: wrong public ISO" >&2
    exit 1
}
[ "$(field repository_suite)" = "$SUITE" ] || { echo "Refusing publication: wrong repository suite" >&2; exit 1; }
[[ "$ISO_HASH" =~ ^[0-9a-f]{64}$ ]] || { echo "Refusing publication: invalid public ISO hash" >&2; exit 1; }
[[ "$COMPLETED_AT" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
    echo "Refusing publication: invalid completion timestamp" >&2
    exit 1
}
[ "$(field packages_sha256)" = "$EXPECTED_HASH" ] || {
    echo "Refusing publication: candidate Packages changed after the VM gate" >&2
    exit 1
}

echo "Published-image upgrade evidence matches candidate Packages: $EXPECTED_HASH"
