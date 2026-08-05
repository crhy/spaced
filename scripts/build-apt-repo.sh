#!/bin/bash
set -euo pipefail

# Build the Spaced Linux apt repository into ./spaced-apt
# (suitable for publishing to GitHub Pages, e.g. https://crhy.github.io/spaced-apt).
#
# Usage: bash scripts/build-apt-repo.sh [output-dir]
# Output defaults to ./spaced-apt
# The repository is unsigned (apt-ftparchive Release without a signature);
# clients reference it with [trusted=yes].

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="${1:-$ROOT/spaced-apt}"
DIST="spaced"
COMP="main"

rm -rf "$OUT"
mkdir -p "$OUT/dists/$DIST/$COMP/binary-amd64"

echo "Building local packages…"
LOCAL_PACKAGE_OUTPUT=/tmp/spaced-apt-build-local \
    bash "$ROOT/scripts/iso/build-local-packages.sh" >/dev/null

cp /tmp/spaced-apt-build-local/*.deb "$OUT/dists/$DIST/$COMP/binary-amd64/"
rm -rf /tmp/spaced-apt-build-local

cd "$OUT/dists/$DIST/$COMP/binary-amd64"

echo "Generating Packages index…"
apt-ftparchive packages . > Packages
gzip -9c Packages > Packages.gz

cd "$OUT/dists/$DIST"
echo "Generating Release metadata…"
apt-ftparchive -o APT::FTPArchive::Release::Origin="Spaced Linux" \
               -o APT::FTPArchive::Release::Label="Spaced Linux apt repository" \
               -o APT::FTPArchive::Release::Suite="$DIST" \
               -o APT::FTPArchive::Release::Codename="$DIST" \
               -o APT::FTPArchive::Release::Architectures="amd64" \
               -o APT::FTPArchive::Release::Components="$COMP" \
               release . > Release

echo "Repository written to $OUT"
