#!/bin/bash
# Build the Spaced xkill cursor (issue #356). xkill grabs the pointer with the
# X11 font cursor XC_pirate, which a cursor theme supplies through a file named
# "pirate". Adwaita has no pirate glyph, so X falls back to a tiny monochrome
# mark; this draws a big red X for each size and packs it with xcursorgen.
# Run when preparing the spaced-cursors payload; the binary output is committed.
set -euo pipefail
cd "$(dirname "$0")/../.."

WORK=$(mktemp -d .strata/build-xkill-cursor.XXXXXX)
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

out=overlays/usr/share/icons/Spaced-Cursors/cursors
mkdir -p "$out"

config="$WORK/config"
: > "$config"

for N in 24 32 48 64; do
    m=$((N / 8))
    off=$((N / 16))
    redw=$((N / 5))
    whitew=$((N / 20))
    half=$((redw / 2))
    png="$WORK/pirate-$N.png"

    # One thick line with round caps: the stroke plus a filled disc at each end.
    add_line() {
        local x1=$1 y1=$2 x2=$3 y2=$4 color=$5 width=$6
        local r=$((width / 2))
        args+=( -stroke "$color" -strokewidth "$width" -fill none \
            -draw "line $x1,$y1 $x2,$y2" )
        args+=( -stroke none -fill "$color" \
            -draw "circle $x1,$y1 $((x1 + r)),$y1" \
            -draw "circle $x2,$y2 $((x2 + r)),$y2" )
    }

    args=( -size "${N}x${N}" xc:none )
    # Black shadow X, offset down-right by N/16.
    add_line $((m + off)) $((m + off)) $((N - m + off)) $((N - m + off)) black "$redw"
    add_line $((N - m + off)) $((m + off)) $((m + off)) $((N - m + off)) black "$redw"
    # Thick red X, margin N/8, round caps.
    add_line "$m" "$m" $((N - m)) $((N - m)) '#d01010' "$redw"
    add_line $((N - m)) "$m" "$m" $((N - m)) '#d01010' "$redw"
    # Thin white highlight along the upper edge of each red stroke.
    add_line $((m + half)) $((m - half)) $((N - m + half)) $((N - m - half)) white "$whitew"
    add_line $((N - m - half)) $((m - half)) $((m - half)) $((N - m - half)) white "$whitew"

    magick "${args[@]}" "$png"
    echo "$N $((N / 2)) $((N / 2)) $png" >> "$config"
done

xcursorgen "$config" "$out/pirate"
