#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUTPUT="${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/cache/local-packages}"
VERSION="$(cat "$ROOT/VERSION")"

mkdir -p "$OUTPUT"

build() {
    local pkg="$1"
    local dir="$ROOT/packages/$pkg"
    local control="$dir/DEBIAN/control"
    # Use the version from debrelease/VERSION unless the control file pins one.
    local ver="$VERSION"
    if grep -q '^Version:' "$control"; then
        ver="$(awk -F': ' '/^Version:/{print $2; exit}' "$control")"
    fi
    local out="$OUTPUT/${pkg}_${ver}_all.deb"
    rm -f "$out"
    dpkg-deb --root-owner-group --build "$dir" "$out"
    dpkg-deb --info "$out" | sed -n '1,12p'
    echo "    -> $out"
}

build spaced-mate-default-settings
build spaced-meta