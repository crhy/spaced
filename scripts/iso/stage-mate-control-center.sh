#!/bin/bash
# Stage rebuilt MATE Control Center packages for the ISO and APT repository.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_MATE_CONTROL_CENTER_ARTIFACT_DIR:-$ROOT/build/mate-control-center/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=1.28.1-1+spaced10.26.7
files=()
for package in mate-control-center mate-control-center-common; do
    arch=amd64
    [[ $package != mate-control-center-common ]] || arch=all
    file="$ARTIFACTS/${package}_${VERSION}_${arch}.deb"
    [[ -f $file ]] || { echo "Missing MATE Control Center rebuild: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == "$arch" ]]
    files+=("$file")
done
[[ ${1:-} != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "${files[@]}" "$OUTPUT/"
