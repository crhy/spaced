#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE="$ROOT/packages/spaced-mate-default-settings"
OUTPUT="$ROOT/build/cache/local-packages"

mkdir -p "$OUTPUT"

rm -f "$OUTPUT"/spaced-mate-default-settings_*.deb

dpkg-deb \
    --root-owner-group \
    --build "$SOURCE" \
    "$OUTPUT/spaced-mate-default-settings_7.26.1_all.deb"

dpkg-deb --info \
    "$OUTPUT/spaced-mate-default-settings_7.26.1_all.deb"
