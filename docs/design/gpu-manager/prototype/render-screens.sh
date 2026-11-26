#!/bin/bash
# Render every designed page to a PNG under Xvfb, in the real Spaced Linux Dark and
# Spaced Linux Light themes (the themes come from this checkout's overlays; the app's
# own screenshot of its window is captured — never the real desktop).
# Output: docs/design/gpu-manager/screens/<page>-<theme>.png
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
SCREENS="$HERE/../screens"
THEME_SHARE="$REPO/overlays/usr/share"
mkdir -p "$SCREENS"

render() {
    local page="$1" gtk_theme="$2" palette="$3" suffix="$4"
    env NO_AT_BRIDGE=1 GTK_THEME="$gtk_theme" \
        XDG_DATA_DIRS="$THEME_SHARE:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" \
        xvfb-run -a python3 "$HERE/gpu_manager_prototype.py" \
            --capture "$page" --palette "$palette" \
            --out "$SCREENS/$page-$suffix.png"
}

for page in first-run overview roles move-monitor drivers; do
    render "$page" Spaced-Linux-Dark dark spaced-dark
    render "$page" Spaced-Linux-Light light light
done

ls -1 "$SCREENS"/*.png
