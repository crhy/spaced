#!/bin/bash
# Rebuild Devuan's xorg-server with the upstream revert of the 21.1.25
# DamageRec ABI break, which crashes the amdgpu driver (issue #298).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MODE=${1:---build}
case "$MODE" in
    --build|--prepare-only) ;;
    *) echo "Usage: $0 [--build|--prepare-only] [output-directory]" >&2; exit 2 ;;
esac
OUTPUT=${2:-$ROOT/build/xorg-server}
mkdir -p "$OUTPUT"
OUTPUT=$(cd "$OUTPUT" && pwd)
PATCHES="$ROOT/patches/xorg-server"
VERSION=2:21.1.25-1devuan1+spaced10.26.3
for tool in curl sha256sum dpkg-source patch; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

mkdir -p "$OUTPUT/downloads"
while read -r digest filename; do
    [ -n "$filename" ] || continue
    target="$OUTPUT/downloads/$filename"
    if ! { [ -f "$target" ] && printf '%s  %s\n' "$digest" "$target" | sha256sum --check --status; }; then
        curl --fail --silent --show-error --location --retry 3 --connect-timeout 30 --max-time 600 \
            "https://mirror.hootsoftware.com/devuan/merged/pool/DEVUAN/main/x/xorg-server/$filename" -o "$target.part"
        printf '%s  %s\n' "$digest" "$target.part" | sha256sum --check --status
        mv "$target.part" "$target"
    fi
done < "$PATCHES/sources.sha256"

build_dir=$(mktemp -d "$OUTPUT/source.XXXXXXXX")
cp "$OUTPUT/downloads/xorg-server_21.1.25.orig.tar.gz" "$build_dir/"
# The descriptor and every archive were verified against the tracked hashes.
dpkg-source --no-check -x "$OUTPUT/downloads/xorg-server_21.1.25-1devuan1.dsc" "$build_dir/xorg-server-21.1.25"
source_dir="$build_dir/xorg-server-21.1.25"
# Format 1.0: debian/rules applies debian/patches/series with quilt.
for patch_file in "$PATCHES"/*.patch; do
    name="spaced-$(basename "$patch_file")"
    cp "$patch_file" "$source_dir/debian/patches/$name"
    printf '%s\n' "$name" >> "$source_dir/debian/patches/series"
done
# Fail now, not halfway through the build, if a patch no longer applies.
check_dir=$(mktemp -d "$OUTPUT/check.XXXXXXXX")
cp -a "$source_dir/." "$check_dir/"
while read -r name; do
    [ -n "$name" ] || continue
    patch -d "$check_dir" -p1 -s --forward < "$source_dir/debian/patches/$name"
done < "$source_dir/debian/patches/series"
if grep -q pListHead "$check_dir/miext/damage/damagestr.h"; then
    echo "DamageRec still carries pListHead after patching" >&2; exit 1
fi
rm -rf "$check_dir"
cat > "$build_dir/changelog" <<EOF
xorg-server ($VERSION) unstable; urgency=medium

  * Revert "damage: Unlink a damage from the list it was actually inserted
    on" (upstream MR 2355, as in Debian 2:21.1.25-2). It changed DamageRec
    without a driver ABI bump, so xf86-video-amdgpu crashed the server at
    startup (Spaced #298, Debian #1150321).

 -- Spaced Linux Developers <dev@spacedlinux.com>  Wed, 14 Oct 2026 00:00:00 +0000

EOF
cat "$source_dir/debian/changelog" >> "$build_dir/changelog"
mv "$build_dir/changelog" "$source_dir/debian/changelog"
printf '%s\n' "$source_dir" > "$OUTPUT/prepared-source"
echo "Prepared xorg-server source: $source_dir"
[ "$MODE" = --prepare-only ] && exit 0

cd "$source_dir"
command -v dpkg-buildpackage >/dev/null || { echo 'Missing dpkg-buildpackage' >&2; exit 1; }
dpkg-checkbuilddeps
dpkg-buildpackage -us -uc -S -nc
dpkg-buildpackage -us -uc -b
mkdir -p "$OUTPUT/artifacts"
for artifact in "$build_dir"/*.deb "$build_dir"/*.dsc "$build_dir"/*.orig.tar.* "$build_dir"/*.diff.gz \
                "$build_dir"/*.changes "$build_dir"/*.buildinfo; do
    [ -f "$artifact" ] || continue
    cp "$artifact" "$OUTPUT/artifacts/"
done
echo "xorg-server packages and source: $OUTPUT/artifacts"
