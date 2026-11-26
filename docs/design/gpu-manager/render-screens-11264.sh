#!/bin/bash
# Render every GPU Manager page to a PNG under Xvfb, in the real Spaced Linux
# Dark and Spaced Linux Light themes, from the REAL app (not the prototype)
# reading the fake bigboy machine (RTX 4070 Ti SUPER desktop, RTX 3050 AI &
# compute on a ×4 link, Radeon 610M Off). The app's own screenshot of its
# window is captured - never the real desktop.
# Output: docs/design/gpu-manager/screens-11264/<page>-<theme>.png
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SCREENS="$HERE/screens-11264"
APP="$REPO/overlays/usr/lib/spaced-linux/spaced-gpu-manager.py"
FAKE="$HERE/fake-bigboy.json"
THEME_SHARE="$REPO/overlays/usr/share"
mkdir -p "$SCREENS"

render() {
    local page="$1" gtk_theme="$2" suffix="$3"
    env NO_AT_BRIDGE=1 GTK_THEME="$gtk_theme" \
        XDG_DATA_DIRS="$THEME_SHARE:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" \
        xvfb-run -a python3 "$APP" \
            --fake-data "$FAKE" --capture "$page" \
            --out "$SCREENS/$page-$suffix.png"
}

for page in first-run overview roles move drivers; do
    render "$page" Spaced-Linux-Dark spaced-dark
    render "$page" Spaced-Linux-Light light
done

ls -1 "$SCREENS"/*.png
