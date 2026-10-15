#!/bin/bash
# Stage the rebuilt xorg-server packages (amdgpu ABI fix, issue #298) for the ISO and the APT repository.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_XORG_ARTIFACT_DIR:-$ROOT/build/xorg-server/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=2:21.1.25-1devuan1+spaced10.26.3
FILE_VERSION=${VERSION#*:}
files=()
# Every binary of the source ships together, so no system mixes the broken
# and the fixed server (xserver-common and the servers pin each other).
for package in xserver-common xserver-xorg-core xserver-xorg-dev xserver-xorg-legacy \
               xvfb xnest xserver-xephyr xorg-server-source; do
    arch=amd64
    [[ "$package" != xserver-common && "$package" != xorg-server-source ]] || arch=all
    file="$ARTIFACTS/${package}_${FILE_VERSION}_${arch}.deb"
    [[ -f "$file" ]] || { echo "Missing xorg-server rebuild: $file. Run make marco first." >&2; exit 1; }
    [[ $(dpkg-deb -f "$file" Package) == "$package" ]]
    [[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
    [[ $(dpkg-deb -f "$file" Architecture) == "$arch" ]]
    files+=("$file")
done
[[ "${1:-}" != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "${files[@]}" "$OUTPUT/"
