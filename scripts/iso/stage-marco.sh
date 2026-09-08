#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_MARCO_ARTIFACT_DIR:-$ROOT/build/marco/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=1.26.2-6+spaced9.26.1
for package in libmarco-private2 marco marco-common; do
    arch=amd64
    [[ "$package" != marco-common ]] || arch=all
    file="$ARTIFACTS/${package}_${VERSION}_${arch}.deb"
    [[ -f "$file" ]] || { echo "Missing Marco backport: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == "$arch" ]]
done
[[ "${1:-}" != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "$ARTIFACTS/libmarco-private2_${VERSION}_amd64.deb" \
    "$ARTIFACTS/marco_${VERSION}_amd64.deb" \
    "$ARTIFACTS/marco-common_${VERSION}_all.deb" "$OUTPUT/"
