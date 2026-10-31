#!/bin/bash
# Stage the rebuilt Caja packages (upstream cross-filesystem rename fix) for the ISO and the APT repository.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_CAJA_ARTIFACT_DIR:-$ROOT/build/caja/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=1.26.4-3+spaced10.26.8
FILE_VERSION=${VERSION#*:}
files=()
# The binary packages depend on each other by exact version, so all of them ship together.
for package in caja caja-common libcaja-extension1 gir1.2-caja-2.0; do
    arch=amd64
    [[ "$package" != caja-common ]] || arch=all
    file="$ARTIFACTS/${package}_${FILE_VERSION}_${arch}.deb"
    [[ -f "$file" ]] || { echo "Missing Caja rebuild: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == "$arch" ]]
    files+=("$file")
done
[[ "${1:-}" != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "${files[@]}" "$OUTPUT/"
