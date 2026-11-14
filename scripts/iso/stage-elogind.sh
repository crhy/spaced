#!/bin/bash
# Stage the coordinated elogind runtime rebuild for the image and APT archive.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_ELOGIND_ARTIFACT_DIR:-$ROOT/build/elogind/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
BASE_VERSION=257.13-1
RELEASE_VERSION=$(<"$ROOT/VERSION")
VERSION="${BASE_VERSION}+spaced${RELEASE_VERSION}"
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
# A release rebuild can reuse build/local-packages.  Remove only older versions
# of this coordinated set so live-build cannot see a mixed elogind repository.
for package in elogind libelogind0 libelogind-compat libpam-elogind; do
    find "$OUTPUT" -maxdepth 1 -type f -name "${package}_*_amd64.deb" \
        ! -name "${package}_${FILE_VERSION}_amd64.deb" -delete
done
cp "${files[@]}" "$OUTPUT/"
