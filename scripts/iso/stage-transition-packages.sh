#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUTPUT="${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}"
MIRROR="${SPACED_DEVUAN_MIRROR:-http://mirror.hootsoftware.com/devuan/merged}"

# Ceres briefly published xkb-data 2.48 while keyboard-configuration 1.248
# still requires xkb-data >= 2.47~ and << 2.47A. Keep the compatible package
# in live-build's local repository until console-setup advances past 1.248.
PACKAGE=xkb-data_2.47-1_all.deb
SHA256=18f9d6c6999767fdde091b03fdddc635d2b4f7ec3dbb210621c9f2062b7ef1cb
URL="$MIRROR/pool/DEBIAN/main/x/xkeyboard-config/$PACKAGE"
DEST="$OUTPUT/$PACKAGE"
TEMP="$DEST.part"

mkdir -p "$OUTPUT"
if [ -f "$DEST" ] && printf '%s  %s\n' "$SHA256" "$DEST" | sha256sum -c - >/dev/null; then
    echo "Using cached Ceres transition package: $DEST"
    exit 0
fi

trap 'rm -f "$TEMP"' EXIT
curl --fail --location --retry 3 --retry-all-errors --connect-timeout 15 \
    --output "$TEMP" "$URL"
printf '%s  %s\n' "$SHA256" "$TEMP" | sha256sum -c -
mv "$TEMP" "$DEST"
echo "Staged Ceres transition package: $DEST"
