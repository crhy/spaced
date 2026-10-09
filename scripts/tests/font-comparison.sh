#!/usr/bin/env bash
# Compare default UI fonts side by side (issue #286). Renders a card per installed family,
# measures width + x-height, builds a contact sheet and a README table. Changes no default.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="$repo_root/docs/font-comparison"
mkdir -p "$out"

targets=(Sans "Nimbus Sans" "DejaVu Sans" "Liberation Sans" "Noto Sans" Cantarell Ubuntu Inter Roboto "Open Sans" "Source Sans 3" Lato "Fira Sans" Carlito FreeSans "Bitstream Vera Sans")

installed=()
missing=()
for fam in "${targets[@]}"; do
    if fc-list : family | grep -qxF "$fam"; then
        installed+=("$fam")
    else
        missing+=("$fam")
    fi
done

work="$(mktemp -d /tmp/spaced-font-cmp.XXXXXX)"
HOME="$work/home" XDG_CONFIG_HOME="$work/config" \
    xvfb-run -a python3 "$repo_root/scripts/tests/font-comparison.py" "$out" "${installed[@]}"
rm -rf "$work"

echo "installed: ${installed[*]}"
echo "not installed (not compared): ${missing[*]}"
