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
    local page="$1" palette="$2" suffix="$3"
    # --palette forces the family navy (dark) or light tokens so the page and
    # cards paint the Spaced navy family everywhere; a grey desktop theme can
    # never make these cards grey. GDK_PIXBUF_MODULE_FILE lets the SVG icons
    # load under Xvfb. The app captures its own window, never the desktop.
    env NO_AT_BRIDGE=1 \
        GDK_PIXBUF_MODULE_FILE="${GDK_PIXBUF_MODULE_FILE:-/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders.cache}" \
        XDG_DATA_DIRS="$THEME_SHARE:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" \
        xvfb-run -a python3 "$APP" \
            --capture "$page" --palette "$palette" --fake \
            --out "$SCREENS/$page-$suffix.png"
}

for page in output input applications effects advanced; do
    render "$page" dark spaced-dark
    render "$page" light light
done

ls -1 "$SCREENS"/*.png
