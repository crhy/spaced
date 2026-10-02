#!/bin/bash
# Compile the nm-applet password focus module (issue #234). Runs inside the
# isolated Ceres build chroot, which already has the GTK 3 headers for Marco.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUTPUT=${1:-$ROOT/build/nm-focus}
mkdir -p "$OUTPUT"
# shellcheck disable=SC2046 # pkg-config prints separate compiler arguments.
gcc -shared -fPIC -O2 -Wall -Wextra -Werror -Wno-unused-parameter \
    -ffile-prefix-map="$ROOT"=. \
    $(pkg-config --cflags gtk+-3.0) \
    -o "$OUTPUT/libspaced-nm-focus.so.part" \
    "$ROOT/src/spaced-nm-focus/spaced-nm-focus.c" \
    $(pkg-config --libs gtk+-3.0)
strip --strip-unneeded "$OUTPUT/libspaced-nm-focus.so.part"
mv "$OUTPUT/libspaced-nm-focus.so.part" "$OUTPUT/libspaced-nm-focus.so"
echo "nm-applet focus module: $OUTPUT/libspaced-nm-focus.so"
