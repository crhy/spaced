#!/bin/bash
# Publish one already-built package into the local Spaced apt repository clone.
#
# scripts/build-apt-repo.sh rebuilds every staged component first, which needs
# the full Marco/Compiz/Caja artifact set. A component released from its own
# repository (see components/) already has a signed GitHub release asset, so
# this script adds that single file and regenerates the metadata exactly the
# same way: same index generator, same Filename rewrite, same pinned key.
#
# Usage: bash scripts/publish-apt-package.sh PACKAGE.deb [APT_REPO_DIR]
# APT_REPO_DIR defaults to ./spaced-apt (a clone of crhy/spaced-apt).
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEB=$(realpath "${1:?Usage: publish-apt-package.sh PACKAGE.deb [APT_REPO_DIR]}")
OUT="${2:-$ROOT/spaced-apt}"
DIST=${SPACED_APT_SUITE:-spaced}
COMP=main
SIGNING_KEY=${SPACED_APT_SIGNING_KEY:-6C16F77C2DAE19D262CFD9F0CC05F885576EBB05}

die() {
    printf 'publish-apt-package: %s\n' "$*" >&2
    exit 1
}

case "$DIST" in spaced|spaced-testing) ;; *) die "unknown archive suite: $DIST" ;; esac

# A published archive must expire when it stops being republished, so a frozen,
# replayed or unsynced copy cannot be installed forever. 180 days is deliberate:
# Spaced publishes about monthly, and an expired Release breaks apt update.
VALID_DAYS=${SPACED_APT_VALID_DAYS:-180}
[[ "$VALID_DAYS" =~ ^[1-9][0-9]*$ ]] ||
    die "SPACED_APT_VALID_DAYS must be a positive integer, got: $VALID_DAYS"

[[ -d "$OUT/.git" ]] || die "$OUT is not a clone of crhy/spaced-apt; clone it first"
[[ -f "$DEB" ]] || die "no such package: $DEB"

# Refuse a substituted signing identity before touching repository metadata.
key_fingerprint=$(gpg --batch --show-keys --with-colons \
    "$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg" \
    | awk -F: '$1 == "fpr" {print $10; exit}')
[[ "$SIGNING_KEY" == "$key_fingerprint" ]] || die "signing key does not match the shipped archive key"
gpg --batch --list-secret-keys "$SIGNING_KEY" >/dev/null

package=$(dpkg-deb -f "$DEB" Package)
version=$(dpkg-deb -f "$DEB" Version)
arch=$(dpkg-deb -f "$DEB" Architecture)
[[ -n $package && -n $version && -n $arch ]] || die "cannot read Package, Version and Architecture from $DEB"
[[ $arch == all || $arch == amd64 ]] ||
    die "architecture '$arch' is not published by this repository (amd64 or all)"

binary_dir="$OUT/dists/$DIST/$COMP/binary-amd64"
source_dir="$OUT/dists/$DIST/$COMP/source"
[[ -d $binary_dir ]] || die "repository has no $binary_dir"
destination="$binary_dir/${package}_${version}_${arch}.deb"

# Never republish different bytes under a Debian version that is already out.
if [[ -e "$destination" ]] && ! cmp -s "$DEB" "$destination"; then
    die "refusing to replace published bytes: $destination. Bump the package version."
fi

work=$(mktemp -d)
cleanup() {
    rm -rf -- "$work"
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$work/metadata/$COMP/binary-amd64" "$work/metadata/$COMP/source" "$work/verify-key"
chmod 0700 "$work/verify-key"

cp "$DEB" "$destination"
chmod 0644 "$destination"

echo "Indexing $package $version ($arch)…"
(cd "$binary_dir" && apt-ftparchive packages .) > "$work/metadata/$COMP/binary-amd64/Packages"
# Filename must be relative to the repository root, not binary-amd64.
sed -i "s|^Filename: \./|Filename: dists/$DIST/$COMP/binary-amd64/|" \
    "$work/metadata/$COMP/binary-amd64/Packages"
gzip -n9c "$work/metadata/$COMP/binary-amd64/Packages" > \
    "$work/metadata/$COMP/binary-amd64/Packages.gz"

(cd "$source_dir" && apt-ftparchive sources .) > "$work/metadata/$COMP/source/Sources"
sed -i "s|^Directory: \.$|Directory: dists/$DIST/$COMP/source|" \
    "$work/metadata/$COMP/source/Sources"
gzip -n9c "$work/metadata/$COMP/source/Sources" > \
    "$work/metadata/$COMP/source/Sources.gz"

echo "Signing repository metadata…"
(cd "$work/metadata" && apt-ftparchive \
    -o APT::FTPArchive::Release::Origin="Spaced Linux" \
    -o APT::FTPArchive::Release::Label="Spaced Linux apt repository" \
    -o APT::FTPArchive::Release::Suite="$DIST" \
    -o APT::FTPArchive::Release::Codename="$DIST" \
    -o APT::FTPArchive::Release::Architectures="amd64" \
    -o APT::FTPArchive::Release::Components="$COMP" \
    -o APT::FTPArchive::Release::ValidTime=$((VALID_DAYS * 86400)) \
    release . > "$work/Release")
gpg --batch --yes --local-user "$SIGNING_KEY" --digest-algo SHA256 \
    --clearsign --output "$work/InRelease" "$work/Release"
gpg --batch --yes --local-user "$SIGNING_KEY" --digest-algo SHA256 \
    --armor --detach-sign --output "$work/Release.gpg" "$work/Release"
gpg --batch --homedir "$work/verify-key" --no-default-keyring \
    --keyring "$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg" \
    --verify "$work/InRelease" >/dev/null

cp "$work/metadata/$COMP/binary-amd64/Packages" \
   "$work/metadata/$COMP/binary-amd64/Packages.gz" "$binary_dir/"
cp "$work/metadata/$COMP/source/Sources" \
   "$work/metadata/$COMP/source/Sources.gz" "$source_dir/"
cp "$work/Release" "$work/Release.gpg" "$work/InRelease" "$OUT/dists/$DIST/"

# Prove the published index describes the file that is actually on disk.
grep -q "^Filename: dists/$DIST/$COMP/binary-amd64/${package}_${version}_${arch}.deb$" \
    "$binary_dir/Packages" || die "index does not list the published package"
published_sha256=$(awk -v pkg="$package" -v ver="$version" '
    $1 == "Package:" { p = $2 }
    $1 == "Version:" { v = $2 }
    $1 == "SHA256:" && p == pkg && v == ver { print $2; exit }' "$binary_dir/Packages")
local_sha256=$(sha256sum "$destination" | awk '{print $1}')
[[ $published_sha256 == "$local_sha256" ]] ||
    die "index SHA256 ($published_sha256) does not match the published file ($local_sha256)"

printf 'Published %s %s (%s) into %s\n' "$package" "$version" "$arch" "$OUT"
printf 'Index entry verified: SHA256 %s\n' "$local_sha256"
printf 'Next: cd %s && git add -A && git commit -m "Publish %s %s" && git push\n' \
    "$OUT" "$package" "$version"
