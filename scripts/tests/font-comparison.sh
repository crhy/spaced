#!/usr/bin/env bash
# Compare default UI fonts side by side (issue #286). Renders a card per available family,
# measures width, x-height and line height, and builds a contact sheet and a README table.
# Changes no default.
#
# Candidates that are not installed can still be compared: unpack their font packages with
# `dpkg-deb -x` into a directory and pass it as FONT_DIR.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="$repo_root/docs/font-comparison"
mkdir -p "$out"

targets=("DejaVu Sans" "Nimbus Sans" "Liberation Sans" "Noto Sans" Cantarell Ubuntu Inter Roboto "Roboto Condensed" "Open Sans" "Source Sans 3" Lato Carlito FreeSans)

if [[ -n "${FONT_DIR:-}" ]]; then
    work="$(mktemp -d /tmp/spaced-font-cmp.XXXXXX)"
    trap 'rm -rf "$work"' EXIT
    cat > "$work/fonts.conf" <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>$FONT_DIR</dir>
  <cachedir>$work/cache</cachedir>
</fontconfig>
EOF
    export FONTCONFIG_FILE="$work/fonts.conf"
fi

rm -f "$out"/*.png
python3 "$repo_root/scripts/tests/font-comparison.py" "$out" "${targets[@]}"
