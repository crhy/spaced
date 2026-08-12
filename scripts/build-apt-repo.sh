#!/bin/bash
set -euo pipefail

# Build the Spaced Linux apt repository into ./spaced-apt
# (suitable for publishing to GitHub Pages, e.g. https://crhy.github.io/spaced-apt).
#
# Usage: bash scripts/build-apt-repo.sh [output-dir]
# Output defaults to ./spaced-apt
# The repository is unsigned (apt-ftparchive Release without a signature);
# clients reference it with [trusted=yes].
#
# When the output directory is a git checkout, the working tree is reset with
# git clean so the index, signature-free Release, and package set are always
# regenerated from the current tree without touching the checkout's history.

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="${1:-$ROOT/spaced-apt}"
DIST="spaced"
COMP="main"

if [ -d "$OUT/.git" ]; then
    git -C "$OUT" clean -fdx -q
else
    rm -rf "$OUT"
fi
mkdir -p "$OUT/dists/$DIST/$COMP/binary-amd64"
OUT=$(cd "$OUT" && pwd)

echo "Building local packages…"
LOCAL_PACKAGE_OUTPUT=/tmp/spaced-apt-build-local \
    bash "$ROOT/scripts/iso/build-local-packages.sh" >/dev/null

# A snapshot repository carries only the current release set, exactly like the
# published index; prune every other version beside the fresh build.
VERSION="$(cat "$ROOT/VERSION")"
find "$OUT/dists/$DIST/$COMP/binary-amd64" -maxdepth 1 -type f \
    -name '*.deb' ! -name "*_${VERSION}_all.deb" -delete

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
