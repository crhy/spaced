#!/bin/bash
# Stage the rebuilt Compiz extra plug-ins package (Fire Writing grab fix) for the ISO and the APT repository.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_COMPIZ_PLUGINS_EXTRA_ARTIFACT_DIR:-$ROOT/build/compiz-plugins-extra/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=2:0.8.18-5+spaced11.26.2
FILE_VERSION=${VERSION#*:}
files=()
# Ship the rebuilt runtime package; debug symbols stay in the build artifacts.
for package in compiz-plugins-extra; do
    arch=amd64
    file="$ARTIFACTS/${package}_${FILE_VERSION}_${arch}.deb"
    [[ -f "$file" ]] || { echo "Missing Compiz extra plug-ins rebuild: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == "$arch" ]]
    files+=("$file")
done
[[ "${1:-}" != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "${files[@]}" "$OUTPUT/"
