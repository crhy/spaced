#!/bin/bash
set -euo pipefail

# Build the Spaced Linux apt repository into ./spaced-apt
# (suitable for publishing to GitHub Pages, e.g. https://crhy.github.io/spaced-apt).
#
# Usage: bash scripts/build-apt-repo.sh [output-dir]
# Output defaults to ./spaced-apt
# Metadata is signed by the same pinned Spaced key delivered in the image.
# Old package files remain available to clients holding an earlier index.

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="${1:-$ROOT/spaced-apt}"
DIST=${SPACED_APT_SUITE:-spaced}
case "$DIST" in spaced|spaced-testing) ;; *) echo "Unknown Spaced archive suite: $DIST" >&2; exit 2 ;; esac
COMP="main"
SIGNING_KEY=${SPACED_APT_SIGNING_KEY:-6C16F77C2DAE19D262CFD9F0CC05F885576EBB05}

mkdir -p "$OUT/dists/$DIST/$COMP/binary-amd64"
OUT=$(cd "$OUT" && pwd)

package_work=$(mktemp -d)
cleanup() {
    rm -rf -- "$package_work"
}
trap cleanup EXIT HUP INT TERM

# Refuse a substituted signing identity before touching repository metadata.
key_fingerprint=$(gpg --batch --show-keys --with-colons \
    "$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg" \
    | awk -F: '$1 == "fpr" {print $10; exit}')
[[ "$SIGNING_KEY" == "$key_fingerprint" ]] || {
    echo "Signing key does not match the shipped archive key" >&2; exit 1;
}
gpg --batch --list-secret-keys "$SIGNING_KEY" >/dev/null
metadata=$package_work/metadata
mkdir -p "$metadata/$COMP/binary-amd64" "$metadata/$COMP/source" "$package_work/verify-key"
chmod 0700 "$package_work/verify-key"

echo "Staging verified standalone release artifacts…"
SPACED_TARGET_ARCH=amd64 \
SPACED_IMAGE_ROOT="$package_work/image" \
SPACED_EXTERNAL_STAGE_DIR="$package_work/external" \
LOCAL_PACKAGE_OUTPUT="$package_work/packages" \
    bash "$ROOT/scripts/iso/stage-external-artifacts.sh" >/dev/null

echo "Building local packages…"
SPACED_EXTERNAL_STAGE_DIR="$package_work/external" \
LOCAL_PACKAGE_OUTPUT="$package_work/packages" \
    bash "$ROOT/scripts/iso/build-local-packages.sh" >/dev/null

for package in "$package_work/packages"/*.deb; do
    destination="$OUT/dists/$DIST/$COMP/binary-amd64/${package##*/}"
    if [[ -e "$destination" ]] && ! cmp -s "$package" "$destination"; then
        echo "Refusing to replace published package bytes: $destination. Bump its version." >&2
        exit 1
    fi
    cp "$package" "$destination"
done

cd "$OUT/dists/$DIST/$COMP/binary-amd64"

echo "Generating Packages index…"
apt-ftparchive packages . > "$metadata/$COMP/binary-amd64/Packages"
# Filename must be relative to the repository root (where apt resolves
# downloads from), not the binary-amd64 directory.
sed -i "s|^Filename: \./|Filename: dists/$DIST/$COMP/binary-amd64/|" "$metadata/$COMP/binary-amd64/Packages"
gzip -n9c "$metadata/$COMP/binary-amd64/Packages" > "$metadata/$COMP/binary-amd64/Packages.gz"

# Publish the corresponding patched Marco sources beside the binaries.
# Keep old source archives immutable just like the binary packages.
source_dir="$OUT/dists/$DIST/$COMP/source"
mkdir -p "$source_dir"
marco_artifacts=${SPACED_MARCO_ARTIFACT_DIR:-$ROOT/build/marco/artifacts}
for source in "$marco_artifacts"/marco_*.dsc "$marco_artifacts"/marco_*.orig.tar.* "$marco_artifacts"/marco_*.debian.tar.*; do
    [[ -f "$source" ]] || { echo "Missing corresponding Marco source: $source" >&2; exit 1; }
    destination="$source_dir/${source##*/}"
    if [[ -e "$destination" ]] && ! cmp -s "$source" "$destination"; then
        echo "Refusing to replace published source bytes: $destination" >&2; exit 1
    fi
    cp "$source" "$destination"
done
(cd "$source_dir" && apt-ftparchive sources .) > "$metadata/$COMP/source/Sources"
sed -i "s|^Directory: \.$|Directory: dists/$DIST/$COMP/source|" "$metadata/$COMP/source/Sources"
gzip -n9c "$metadata/$COMP/source/Sources" > "$metadata/$COMP/source/Sources.gz"

cd "$metadata"
echo "Generating Release metadata…"
apt-ftparchive -o APT::FTPArchive::Release::Origin="Spaced Linux" \
               -o APT::FTPArchive::Release::Label="Spaced Linux apt repository" \
               -o APT::FTPArchive::Release::Suite="$DIST" \
               -o APT::FTPArchive::Release::Codename="$DIST" \
               -o APT::FTPArchive::Release::Architectures="amd64" \
               -o APT::FTPArchive::Release::Components="$COMP" \
               release . > "$package_work/Release"
gpg --batch --yes --local-user "$SIGNING_KEY" --digest-algo SHA256 \
    --clearsign --output "$package_work/InRelease" "$package_work/Release"
gpg --batch --yes --local-user "$SIGNING_KEY" --digest-algo SHA256 \
    --armor --detach-sign --output "$package_work/Release.gpg" "$package_work/Release"
gpg --batch --homedir "$package_work/verify-key" --no-default-keyring \
    --keyring "$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg" \
    --verify "$package_work/InRelease"
cp "$metadata/$COMP/binary-amd64/Packages" "$metadata/$COMP/binary-amd64/Packages.gz" \
    "$OUT/dists/$DIST/$COMP/binary-amd64/"
cp "$metadata/$COMP/source/Sources" "$metadata/$COMP/source/Sources.gz" "$source_dir/"
cp "$package_work/Release" "$package_work/Release.gpg" "$package_work/InRelease" "$OUT/dists/$DIST/"

echo "Repository written to $OUT"
