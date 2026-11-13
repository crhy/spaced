#!/bin/bash
# Stage the coordinated elogind runtime rebuild for the image and APT archive.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_ELOGIND_ARTIFACT_DIR:-$ROOT/build/elogind/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=257.13-1+spaced11.26.1
FILE_VERSION=${VERSION#*:}
files=()
for package in elogind libelogind0 libelogind-compat libpam-elogind; do
    file="$ARTIFACTS/${package}_${FILE_VERSION}_amd64.deb"
    [[ -f "$file" ]] || { echo "Missing elogind rebuild: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == amd64 ]]
    files+=("$file")
done
[[ "${1:-}" != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "${files[@]}" "$OUTPUT/"
