#!/bin/bash
# Build the Spaced xkill cursor (issue #356). xkill grabs the pointer with the
# X11 font cursor XC_pirate, which a cursor theme supplies through a file named
# "pirate". Adwaita has no pirate glyph, so X falls back to a tiny monochrome
# mark. Render the maintained SVG at each cursor size and pack it with
# xcursorgen. The source artwork declares its hotspot at the exact centre.
# Run when preparing the spaced-cursors payload; the binary output is committed.
set -euo pipefail
cd "$(dirname "$0")/../.."

WORK=$(mktemp -d)
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

out=overlays/usr/share/icons/Spaced-Cursors/cursors
mkdir -p "$out"

config="$WORK/config"
: > "$config"
source_svg=branding/cursors/xkillcursor.svg

if ! command -v rsvg-convert >/dev/null 2>&1; then
    echo "error: rsvg-convert is required to build the xkill cursor" >&2
    exit 1
fi
if ! command -v xcursorgen >/dev/null 2>&1; then
    echo "error: xcursorgen is required to build the xkill cursor" >&2
    exit 1
fi

for N in 24 32 48 64; do
    png="$WORK/pirate-$N.png"

    rsvg-convert --width "$N" --height "$N" "$source_svg" --output "$png"
    echo "$N $((N / 2)) $((N / 2)) $png" >> "$config"
done

xcursorgen "$config" "$out/pirate"
