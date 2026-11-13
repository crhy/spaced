#!/bin/bash
# Build Devuan elogind with the upstream immediate power-action crash fix.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MODE=${1:---build}
case "$MODE" in
    --build|--prepare-only) ;;
    *) echo "Usage: $0 [--build|--prepare-only] [output-directory]" >&2; exit 2 ;;
esac
OUTPUT=${2:-$ROOT/build/elogind}
mkdir -p "$OUTPUT"
OUTPUT=$(cd "$OUTPUT" && pwd)
PATCHES="$ROOT/patches/elogind"
VERSION=257.13-1+spaced11.26.1
for tool in curl sha256sum dpkg-source patch; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

mkdir -p "$OUTPUT/downloads"
while read -r digest filename; do
    [[ -n "$filename" ]] || continue
    target="$OUTPUT/downloads/$filename"
    if ! { [[ -f "$target" ]] && printf '%s  %s\n' "$digest" "$target" | sha256sum --check --status; }; then
        curl --fail --silent --show-error --location --retry 3 --connect-timeout 30 --max-time 600 \
            "https://mirror.hootsoftware.com/devuan/merged/pool/DEVUAN/main/e/elogind/$filename" -o "$target.part"
        printf '%s  %s\n' "$digest" "$target.part" | sha256sum --check --status
        mv "$target.part" "$target"
    fi
done < "$PATCHES/sources.sha256"

build_dir=$(mktemp -d "$OUTPUT/source.XXXXXXXX")
cp "$OUTPUT/downloads/elogind_257.13.orig.tar.gz" "$build_dir/"
dpkg-source --no-check -x "$OUTPUT/downloads/elogind_257.13-1.dsc" "$build_dir/elogind-257.13"
source_dir="$build_dir/elogind-257.13"
runtime_patch=spaced-fix-poweroff-reboot-segfault.patch
xml_patch=spaced-enable-xml-entity-resolution.patch
cp "$PATCHES/0001-fix-poweroff-reboot-segfault.patch" "$source_dir/debian/patches/$runtime_patch"
cp "$PATCHES/0002-enable-xml-entity-resolution.patch" "$source_dir/debian/patches/$xml_patch"
printf '%s\n%s\n' "$runtime_patch" "$xml_patch" >> "$source_dir/debian/patches/series"
dpkg-source --before-build "$source_dir"
cat > "$build_dir/changelog" <<EOF
elogind ($VERSION) unstable; urgency=medium

  * Backport the upstream fix for the e-poweroff/e-reboot completion crash
    and clean up manager state if the action worker cannot be started.

 -- Spaced Linux Developers <dev@spacedlinux.com>  Fri, 13 Nov 2026 00:00:00 +0000

EOF
cat "$source_dir/debian/changelog" >> "$build_dir/changelog"
mv "$build_dir/changelog" "$source_dir/debian/changelog"
printf '%s\n' "$source_dir" > "$OUTPUT/prepared-source"
echo "Prepared elogind source: $source_dir"
[[ "$MODE" == --prepare-only ]] && exit 0

cd "$source_dir"
command -v dpkg-buildpackage >/dev/null || { echo 'Missing dpkg-buildpackage' >&2; exit 1; }
dpkg-checkbuilddeps
dpkg-source -b .
# test-login interrogates the live login manager and aborts in this deliberately
# service-free package-build chroot.  Build without Debian's all-or-nothing test
# step, then run every other upstream test explicitly.  The installed-VM release
# gate covers the omitted live-service test plus repeated reboot and poweroff.
DEB_BUILD_OPTIONS="${DEB_BUILD_OPTIONS:+$DEB_BUILD_OPTIONS }nocheck" \
    dpkg-buildpackage -us -uc -b
python3 - "$source_dir/build" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

build = Path(sys.argv[1])
tests = json.loads((build / "meson-info/intro-tests.json").read_text())
names = [test["name"] for test in tests if test["name"] != "test-login"]
if len(tests) != 272 or len(names) != 271:
    raise SystemExit(
        f"Unexpected elogind test inventory: {len(tests)} total, {len(names)} selected"
    )
subprocess.run(
    ["meson", "test", "-C", str(build), "--no-rebuild", "--print-errorlogs", *names],
    check=True,
)
PY
mkdir -p "$OUTPUT/artifacts"
for artifact in "$build_dir"/*.deb "$build_dir"/*.dsc "$build_dir"/*.tar.* \
                "$build_dir"/*.changes "$build_dir"/*.buildinfo; do
    [[ -f "$artifact" ]] || continue
    cp "$artifact" "$OUTPUT/artifacts/"
done
echo "elogind packages and source: $OUTPUT/artifacts"
