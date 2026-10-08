#!/bin/bash
# Stage the rebuilt Compiz packages (decorator click-area fix, issue #279) for the ISO and the APT repository.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_COMPIZ_ARTIFACT_DIR:-$ROOT/build/compiz/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=2:0.8.18-9+spaced10.26.2
FILE_VERSION=${VERSION#*:}
files=()
# The binary packages depend on each other by exact version, so all of them ship together.
for package in compiz compiz-core compiz-gnome compiz-mate compiz-plugins libdecoration0t64; do
    arch=amd64
    [[ "$package" != compiz ]] || arch=all
    file="$ARTIFACTS/${package}_${FILE_VERSION}_${arch}.deb"
    [[ -f "$file" ]] || { echo "Missing Compiz rebuild: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == "$arch" ]]
    files+=("$file")
done
[[ "${1:-}" != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "${files[@]}" "$OUTPUT/"
