#!/bin/bash
# Render every built page (Output/Input/Applications/Effects/Advanced) to a PNG
# under Xvfb, in the real Spaced dark and light themes, into
# docs/design/sound-manager/screens-11264/. The app is run with --fake (the
# deterministic bigboy backend): no real sound device is opened, no sound is
# played and no microphone is touched. The app's own window is captured, never
# the real desktop.
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
APP="$REPO/overlays/usr/lib/spaced-linux/spaced-sound-manager.py"
SCREENS="$HERE/screens-11264"
THEME_SHARE="$REPO/overlays/usr/share"
mkdir -p "$SCREENS"

render() {
    local page="$1" gtk_theme="$2" palette="$3" suffix="$4"
    env NO_AT_BRIDGE=1 GTK_THEME="$gtk_theme" \
        XDG_DATA_DIRS="$THEME_SHARE:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" \
        xvfb-run -a python3 "$APP" \
            --capture "$page" --palette "$palette" --fake \
            --out "$SCREENS/$page-$suffix.png"
}

for page in output input applications effects advanced; do
    render "$page" Spaced-Dark dark spaced-dark
    render "$page" Spaced-Linux-Light light light
done

ls -1 "$SCREENS"/*.png
