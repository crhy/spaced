#!/bin/bash
# Build MATE Control Center with reliable application and file shortcut targets (issue #351).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MODE=${1:---build}
case "$MODE" in
    --build|--prepare-only) ;;
    *) echo "Usage: $0 [--build|--prepare-only] [output-directory]" >&2; exit 2 ;;
esac
OUTPUT=${2:-$ROOT/build/mate-control-center}
mkdir -p "$OUTPUT"
OUTPUT=$(cd "$OUTPUT" && pwd)
PATCHES="$ROOT/patches/mate-control-center"
VERSION=1.28.1-1+spaced10.26.7
for tool in curl sha256sum dpkg-source patch; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

mkdir -p "$OUTPUT/downloads"
while read -r digest filename; do
    [[ -n $filename ]] || continue
    target="$OUTPUT/downloads/$filename"
    if ! { [[ -f $target ]] && printf '%s  %s\n' "$digest" "$target" | sha256sum --check --status; }; then
        curl --fail --silent --show-error --location --retry 3 --connect-timeout 30 --max-time 600 \
            "https://mirror.hootsoftware.com/devuan/merged/pool/DEBIAN/main/m/mate-control-center/$filename" \
            -o "$target.part"
        printf '%s  %s\n' "$digest" "$target.part" | sha256sum --check --status
        mv "$target.part" "$target"
    fi
done < "$PATCHES/sources.sha256"

build_dir=$(mktemp -d "$OUTPUT/source.XXXXXXXX")
cp "$OUTPUT/downloads/mate-control-center_1.28.1.orig.tar.xz" "$build_dir/"
dpkg-source --no-check -x "$OUTPUT/downloads/mate-control-center_1.28.1-1.dsc" \
    "$build_dir/mate-control-center-1.28.1"
source_dir="$build_dir/mate-control-center-1.28.1"
for patch_file in "$PATCHES"/*.patch; do
    name="spaced-$(basename "$patch_file")"
    cp "$patch_file" "$source_dir/debian/patches/$name"
    printf '%s\n' "$name" >> "$source_dir/debian/patches/series"
done
dpkg-source --before-build "$source_dir"
# mate-time-admin is built only with the optional systemd integration. The
# Devuan build disables that integration, so its data directory must not
# remain a required entry in Debian's common-package install manifest.
install_manifest="$source_dir/debian/mate-control-center-common.install"
grep -qxF 'usr/share/mate-time-admin/' "$install_manifest"
sed -i '\|^usr/share/mate-time-admin/$|d' "$install_manifest"
cat > "$build_dir/changelog" <<EOF
mate-control-center ($VERSION) unstable; urgency=medium

  * Launch chosen applications by desktop ID and add a shortcut file picker.
  * Backport upstream's fix for libsystemd auto-detection.

 -- Spaced Linux Developers <dev@spacedlinux.com>  Mon, 26 Oct 2026 00:00:00 +0000

EOF
cat "$source_dir/debian/changelog" >> "$build_dir/changelog"
mv "$build_dir/changelog" "$source_dir/debian/changelog"
printf '%s\n' "$source_dir" > "$OUTPUT/prepared-source"
echo "Prepared MATE Control Center source: $source_dir"
[[ $MODE == --prepare-only ]] && exit 0

cd "$source_dir"
command -v dpkg-buildpackage >/dev/null || { echo 'Missing dpkg-buildpackage' >&2; exit 1; }
dpkg-checkbuilddeps
dpkg-source -b .
dpkg-buildpackage -us -uc -b
mkdir -p "$OUTPUT/artifacts"
for artifact in "$build_dir"/*.deb "$build_dir"/*.dsc "$build_dir"/*.tar.* \
                "$build_dir"/*.changes "$build_dir"/*.buildinfo; do
    [[ -f $artifact ]] || continue
    cp "$artifact" "$OUTPUT/artifacts/"
done
echo "MATE Control Center packages and source: $OUTPUT/artifacts"
