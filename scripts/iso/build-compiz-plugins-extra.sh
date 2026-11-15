#!/bin/bash
# Build a tracked source package; never byte-patch installed Compiz plug-ins.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MODE=${1:---build}
case "$MODE" in
    --build|--prepare-only) ;;
    *) echo "Usage: $0 [--build|--prepare-only] [output-directory]" >&2; exit 2 ;;
esac
OUTPUT=${2:-$ROOT/build/compiz-plugins-extra}
mkdir -p "$OUTPUT"
OUTPUT=$(cd "$OUTPUT" && pwd)
PATCHES="$ROOT/patches/compiz-plugins-extra"
VERSION=2:0.8.18-5+spaced11.26.2
for tool in curl sha256sum dpkg-source patch; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

mkdir -p "$OUTPUT/downloads"
while read -r digest filename; do
    [ -n "$filename" ] || continue
    target="$OUTPUT/downloads/$filename"
    if ! { [ -f "$target" ] && printf '%s  %s\n' "$digest" "$target" | sha256sum --check --status; }; then
        curl --fail --silent --show-error --location --retry 3 --connect-timeout 30 --max-time 600 \
            "https://mirror.hootsoftware.com/devuan/merged/pool/DEBIAN/main/c/compiz-plugins-extra/$filename" -o "$target.part"
        printf '%s  %s\n' "$digest" "$target.part" | sha256sum --check --status
        mv "$target.part" "$target"
    fi
done < "$PATCHES/sources.sha256"

build_dir=$(mktemp -d "$OUTPUT/source.XXXXXXXX")
cp "$OUTPUT/downloads/compiz-plugins-extra_0.8.18.orig.tar.xz" "$build_dir/"
# The descriptor and every archive were verified against the tracked hashes.
dpkg-source --no-check -x "$OUTPUT/downloads/compiz-plugins-extra_0.8.18-5.dsc" "$build_dir/compiz-plugins-extra-0.8.18"
source_dir="$build_dir/compiz-plugins-extra-0.8.18"
for patch_file in "$PATCHES"/*.patch; do
    [ -f "$patch_file" ] || continue
    name="spaced-$(basename "$patch_file")"
    cp "$patch_file" "$source_dir/debian/patches/$name"
    printf '%s\n' "$name" >> "$source_dir/debian/patches/series"
done
dpkg-source --before-build "$source_dir"
cat > "$build_dir/changelog" <<EOF
compiz-plugins-extra ($VERSION) unstable; urgency=medium

  * firepaint: release the Fire Writing screen grab for a key press and key
    release, and take it again on the next button press, so a keyboard
    shortcut that needs its own pointer and keyboard grab (Shift+Print runs
    mate-screenshot) produces an image while fire is being painted.

 -- Spaced Linux Developers <dev@spacedlinux.com>  Mon, 16 Nov 2026 00:00:00 +0000

EOF
cat "$source_dir/debian/changelog" >> "$build_dir/changelog"
mv "$build_dir/changelog" "$source_dir/debian/changelog"
printf '%s\n' "$source_dir" > "$OUTPUT/prepared-source"
echo "Prepared Compiz extra plug-ins source: $source_dir"
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
echo "Compiz extra plug-ins packages and source: $OUTPUT/artifacts"
