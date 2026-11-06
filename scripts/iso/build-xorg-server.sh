#!/bin/bash
# Rebuild Devuan's corrected xorg-server source. Devuan's -2 source now
# carries the upstream DamageRec ABI revert, so Spaced must not apply it a
# second time (issues #298 and #401).
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
VERSION=2:21.1.25-2devuan1+spaced11.26
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
dpkg-source --no-check -x "$OUTPUT/downloads/xorg-server_21.1.25-2devuan1.dsc" "$build_dir/xorg-server-21.1.25"
source_dir="$build_dir/xorg-server-21.1.25"
# Format 1.0: verify Devuan's pinned patch series and the restored ABI before
# spending time on a full build.
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

  * Rebase on Devuan 2:21.1.25-2devuan1, which incorporates upstream MR 2355
    and restores the DamageRec driver ABI without a second local patch
    (Spaced #298, #401; Debian #1150321).

 -- Spaced Linux Developers <dev@spacedlinux.com>  Fri, 06 Nov 2026 00:00:00 +0000

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
