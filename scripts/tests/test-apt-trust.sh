#!/bin/bash
# Exercise APT verification against temporary copies of a local signed archive.
# No network sources, package installs, or host APT state are used.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
REPO=$(realpath "${1:?Usage: test-apt-trust.sh SIGNED_REPO}")
SUITE=${SPACED_APT_SUITE:-spaced}
[[ "$SUITE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || exit 2
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
VERSION=$(sed -n 's/^Version: //p' "$ROOT/packages/spaced-meta/DEBIAN/control")
KEY="$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg"
[[ -s "$REPO/dists/$SUITE/InRelease" ]]

new_probe() {
    local name=$1 key=${2:-$KEY}
    PROBE="$WORK/$name"
    mkdir -p "$PROBE"/{lists/partial,archives/partial,empty,downloads}
    : > "$PROBE/status"
    cp -a "$REPO" "$PROBE/repo"
    cat > "$PROBE/sources.list" <<EOF
deb [signed-by=$key] file:$PROBE/repo $SUITE main
EOF
    cat > "$PROBE/apt.conf" <<EOF
Dir::Etc::main "/dev/null";
Dir::Etc::parts "$PROBE/empty";
Dir::Etc::sourcelist "$PROBE/sources.list";
Dir::Etc::sourceparts "$PROBE/empty";
Dir::Etc::preferences "/dev/null";
Dir::Etc::preferencesparts "$PROBE/empty";
Dir::State "$PROBE";
Dir::State::status "$PROBE/status";
Dir::State::lists "$PROBE/lists";
Dir::Cache "$PROBE";
Dir::Cache::archives "$PROBE/archives";
Dir::Cache::pkgcache "";
Dir::Cache::srcpkgcache "";
APT::Architecture "amd64";
APT::Architectures { "amd64"; };
APT::Sandbox::User "$(id -un)";
APT::Update::Error-Mode "any";
EOF
    export APT_CONFIG="$PROBE/apt.conf"
}
expect_rejection() {
    local description=$1
    shift
    if "$@" > "$PROBE/rejection.log" 2>&1; then
        echo "FAIL: $description was accepted" >&2
        exit 1
    fi
    if ! grep -Eqi 'signature|signing key|public key|NO_PUBKEY|not signed|Hash Sum mismatch|unexpected size' "$PROBE/rejection.log"; then
        cat "$PROBE/rejection.log" >&2
        echo "FAIL: $description failed for an unrelated reason" >&2
        exit 1
    fi
    echo "PASS: $description rejected"
}
new_probe valid
apt-get update > "$PROBE/update.log" 2>&1
(cd "$PROBE/downloads" && apt-get download spaced-meta > "$PROBE/download.log" 2>&1)
[[ -s "$PROBE/downloads/spaced-meta_${VERSION}_all.deb" ]]
echo 'PASS: valid signed metadata and package accepted'

new_probe wrong-key "$ROOT/config/keyrings/devuan-archive-keyring.pgp"
expect_rejection 'an unrelated trusted key' apt-get update

new_probe altered-release
sed -i 's/^Label: .*/Label: Altered archive/' "$PROBE/repo/dists/$SUITE/InRelease"
expect_rejection 'altered signed release metadata' apt-get update

new_probe altered-index
printf '\nModified package index\n' >> "$PROBE/repo/dists/$SUITE/main/binary-amd64/Packages"
gzip -n9c "$PROBE/repo/dists/$SUITE/main/binary-amd64/Packages" > "$PROBE/repo/dists/$SUITE/main/binary-amd64/Packages.gz"
expect_rejection 'altered package index' apt-get update

new_probe altered-package
apt-get update > "$PROBE/update.log" 2>&1
printf 'corrupt' >> "$PROBE/repo/dists/$SUITE/main/binary-amd64/spaced-meta_${VERSION}_all.deb"
cd "$PROBE/downloads"
expect_rejection 'altered package payload' apt-get download spaced-meta

echo 'APT authenticity and integrity tests passed.'
