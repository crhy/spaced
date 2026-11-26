#!/bin/bash
# Upgrade the current public ISO from the signed candidate repository, then
# repeat the real two-machine SMB/GVfs and IPP test on upgraded guests.
set -euo pipefail

usage() {
    echo "Usage: published-upgrade-network-gate.sh REPO_DIR [PUBLIC_ISO]" >&2
}

REPO_DIR=${1:-}
PUBLIC_ISO=${2:-}
[ -n "$REPO_DIR" ] || { usage; exit 2; }
[ -d "$REPO_DIR" ] || { echo "APT repository not found: $REPO_DIR" >&2; exit 2; }
REPO_DIR=$(cd "$REPO_DIR" && pwd)

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
VERSION=$(cat "$PROJECT_ROOT/VERSION")
BASE_VERSION=${SPACED_UPGRADE_BASE_VERSION:-$VERSION}
[[ "$BASE_VERSION" =~ ^(1[0-2]|[1-9])\.[0-9]{2}(\.[0-9]+)?$ ]] || {
    echo "Invalid public base version: $BASE_VERSION" >&2
    exit 2
}
ISO_NAME=spaced-linux-$BASE_VERSION-amd64.iso
CACHE_DIR=${SPACED_PUBLIC_ISO_CACHE:-$PROJECT_ROOT/build/cache/published-isos/v$BASE_VERSION}
EVIDENCE=${SPACED_PUBLISHED_UPGRADE_EVIDENCE:-$PROJECT_ROOT/build/test-artifacts/published-upgrade-network/PASS.env}
SUITE=${SPACED_APT_SUITE:-spaced}
PACKAGES=$REPO_DIR/dists/$SUITE/main/binary-amd64/Packages

[ -s "$REPO_DIR/dists/$SUITE/InRelease" ] || { echo "Candidate repository has no signed InRelease" >&2; exit 2; }
[ -s "$PACKAGES" ] || { echo "Candidate repository has no amd64 Packages index" >&2; exit 2; }
for tool in sha256sum date; do
    command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 2; }
done

if [ -z "$PUBLIC_ISO" ]; then
    command -v gh >/dev/null || { echo "gh is required to fetch the public ISO" >&2; exit 2; }
    mkdir -p "$CACHE_DIR"
    gh release download "v$BASE_VERSION" --repo crhy/spaced \
        --pattern "$ISO_NAME" --pattern "$ISO_NAME.sha256" \
        --dir "$CACHE_DIR" --skip-existing
    PUBLIC_ISO=$CACHE_DIR/$ISO_NAME
    CHECKSUM=$CACHE_DIR/$ISO_NAME.sha256
else
    [ -f "$PUBLIC_ISO" ] || { echo "Public ISO not found: $PUBLIC_ISO" >&2; exit 2; }
    PUBLIC_ISO=$(cd "$(dirname "$PUBLIC_ISO")" && pwd)/${PUBLIC_ISO##*/}
    CHECKSUM=$PUBLIC_ISO.sha256
fi

[ -s "$PUBLIC_ISO" ] || { echo "Public ISO is missing: $PUBLIC_ISO" >&2; exit 2; }
[ -s "$CHECKSUM" ] || { echo "Public ISO checksum is missing: $CHECKSUM" >&2; exit 2; }
[ "${PUBLIC_ISO##*/}" = "$ISO_NAME" ] || {
    echo "Expected public base ISO $ISO_NAME, got ${PUBLIC_ISO##*/}" >&2
    exit 2
}
(cd "$(dirname "$PUBLIC_ISO")" && sha256sum -c "${CHECKSUM##*/}")

# Remove prior success before starting; interruption or failure cannot leave a
# stale PASS file that authorizes publication.
mkdir -p "$(dirname "$EVIDENCE")"
rm -f "$EVIDENCE"

"$SCRIPT_DIR/upgrade-test.sh" "$PUBLIC_ISO" "$REPO_DIR"
"$SCRIPT_DIR/network-services-gate.sh" "$PUBLIC_ISO" "$REPO_DIR"

ISO_SHA256=$(sha256sum "$PUBLIC_ISO" | awk '{print $1}')
PACKAGES_SHA256=$(sha256sum "$PACKAGES" | awk '{print $1}')
TEMP_EVIDENCE=$EVIDENCE.tmp.$$
trap 'rm -f "$TEMP_EVIDENCE"' EXIT
cat > "$TEMP_EVIDENCE" <<EOF
result=PASS
version=$VERSION
base_version=$BASE_VERSION
iso_name=$ISO_NAME
iso_sha256=$ISO_SHA256
packages_sha256=$PACKAGES_SHA256
repository_suite=$SUITE
completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
mv "$TEMP_EVIDENCE" "$EVIDENCE"
trap - EXIT

echo "RESULT: PASS public $ISO_NAME upgraded to $VERSION and passed both network-services guests"
echo "Publication evidence: $EVIDENCE"
