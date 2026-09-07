#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
CACHE=${SPACED_EXTERNAL_CACHE_DIR:-$ROOT/build/cache/external-artifacts}
VERSION=0.11.5-1
SHA256=4c35d39d6ce6e60cdd453a84d2c494b23bae6a2bd4d1ca99f33b82f778e46d82
PACKAGE=amdgpu-top_${VERSION}_amd64.deb
URL=https://github.com/Umio-Yasuno/amdgpu_top/releases/download/v0.11.5/amdgpu-top_without_gui_${VERSION}_amd64.deb

mkdir -p "$OUTPUT" "$CACHE"
artifact=$CACHE/$PACKAGE
temporary=$(mktemp "$CACHE/amdgpu-top.XXXXXX")
trap 'rm -f "$temporary"' EXIT
if ! printf '%s  %s\n' "$SHA256" "$artifact" | sha256sum -c - >/dev/null 2>&1; then
    curl --fail --location --proto '=https' --proto-redir '=https' \
        --retry 3 --connect-timeout 15 --max-time 300 --output "$temporary" "$URL"
    printf '%s  %s\n' "$SHA256" "$temporary" | sha256sum -c -
    mv "$temporary" "$artifact"
fi
[[ $(dpkg-deb -f "$artifact" Package) == amdgpu-top ]]
[[ $(dpkg-deb -f "$artifact" Version) == "$VERSION" ]]
[[ $(dpkg-deb -f "$artifact" Architecture) == amd64 ]]
cp "$artifact" "$OUTPUT/$PACKAGE"
