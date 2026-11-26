#!/bin/bash
# Render every designed page to a PNG under Xvfb, in the real Spaced dark and light
# themes (themes come from this checkout's overlays; the app's own window is captured,
# never the real desktop).  No sound is played and no microphone is opened: the
# prototype is fake-data-only and its test-sound path refuses to run.
# Output: docs/design/sound-manager/screens/<page>-<theme>.png
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
        xvfb-run -a python3 "$HERE/sound_manager_prototype.py" \
            --capture "$page" --palette "$palette" --fake \
            --out "$SCREENS/$page-$suffix.png"
}

for page in output input applications effects advanced; do
    render "$page" Spaced-Dark dark spaced-dark
    render "$page" Spaced-Linux-Light light light
done

ls -1 "$SCREENS"/*.png
