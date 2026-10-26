#!/bin/bash
# Stage the rebuilt Brisk Menu for the ISO and APT repository.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ARTIFACTS=${SPACED_BRISK_MENU_ARTIFACT_DIR:-$ROOT/build/brisk-menu/artifacts}
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
VERSION=0.6.2-2+spaced10.26.7
file="$ARTIFACTS/mate-applet-brisk-menu_${VERSION}_amd64.deb"
[[ -f $file ]] || { echo "Missing Brisk Menu rebuild: $file. Run make marco first." >&2; exit 1; }
[[ $(dpkg-deb -f "$file" Package) == mate-applet-brisk-menu ]]
[[ $(dpkg-deb -f "$file" Version) == "$VERSION" ]]
[[ $(dpkg-deb -f "$file" Architecture) == amd64 ]]
[[ ${1:-} != --check ]] || exit 0
mkdir -p "$OUTPUT"
cp "$file" "$OUTPUT/"
