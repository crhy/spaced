#!/bin/bash
# Build a tracked source package; never byte-patch installed MATE libraries.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MODE=${1:---build}
case "$MODE" in
    --build|--prepare-only) ;;
    *) echo "Usage: $0 [--build|--prepare-only] [output-directory]" >&2; exit 2 ;;
esac
OUTPUT=${2:-$ROOT/build/caja}
mkdir -p "$OUTPUT"
OUTPUT=$(cd "$OUTPUT" && pwd)
PATCHES="$ROOT/patches/caja"
VERSION=1.26.4-3+spaced10.26.6
for tool in curl sha256sum dpkg-source patch; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

mkdir -p "$OUTPUT/downloads"
while read -r digest filename; do
    [ -n "$filename" ] || continue
    target="$OUTPUT/downloads/$filename"
    if ! { [ -f "$target" ] && printf '%s  %s\n' "$digest" "$target" | sha256sum --check --status; }; then
        curl --fail --silent --show-error --location --retry 3 --connect-timeout 30 --max-time 600 \
            "https://mirror.hootsoftware.com/devuan/merged/pool/DEBIAN/main/c/caja/$filename" -o "$target.part"
        printf '%s  %s\n' "$digest" "$target.part" | sha256sum --check --status
        mv "$target.part" "$target"
    fi
done < "$PATCHES/sources.sha256"

build_dir=$(mktemp -d "$OUTPUT/source.XXXXXXXX")
cp "$OUTPUT/downloads/caja_1.26.4.orig.tar.xz" "$build_dir/"
# The descriptor and every archive were verified against the tracked hashes.
dpkg-source --no-check -x "$OUTPUT/downloads/caja_1.26.4-3.dsc" "$build_dir/caja-1.26.4"
source_dir="$build_dir/caja-1.26.4"
for patch_file in "$PATCHES"/*.patch; do
    name="spaced-$(basename "$patch_file")"
    cp "$patch_file" "$source_dir/debian/patches/$name"
    printf '%s\n' "$name" >> "$source_dir/debian/patches/series"
done
dpkg-source --before-build "$source_dir"
cat > "$build_dir/changelog" <<EOF
caja ($VERSION) unstable; urgency=medium

  * Preserve renamed destinations across filesystems (MATE Caja PR #1888).

 -- Spaced Linux Developers <dev@spacedlinux.com>  Fri, 23 Oct 2026 00:00:00 +0000

EOF
cat "$source_dir/debian/changelog" >> "$build_dir/changelog"
mv "$build_dir/changelog" "$source_dir/debian/changelog"
printf '%s\n' "$source_dir" > "$OUTPUT/prepared-source"
echo "Prepared Caja source: $source_dir"
[ "$MODE" = --prepare-only ] && exit 0

cd "$source_dir"
command -v dpkg-buildpackage >/dev/null || { echo 'Missing dpkg-buildpackage' >&2; exit 1; }
dpkg-checkbuilddeps
dpkg-source -b .
dpkg-buildpackage -us -uc -b
mkdir -p "$OUTPUT/artifacts"
for artifact in "$build_dir"/*.deb "$build_dir"/*.dsc "$build_dir"/*.tar.* \
                "$build_dir"/*.changes "$build_dir"/*.buildinfo; do
    [ -f "$artifact" ] || continue
    cp "$artifact" "$OUTPUT/artifacts/"
done
echo "Caja packages and source: $OUTPUT/artifacts"
