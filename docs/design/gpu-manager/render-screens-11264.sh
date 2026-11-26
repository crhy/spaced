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
    local page="$1" palette="$2" suffix="$3"
    # --palette forces the family navy (dark) or light tokens so the card/page
    # paint the Spaced navy family on every machine (the desktop's own theme
    # only supplies the window-manager decorations). The navy of --palette dark
    # is the Spaced-Win11-Dark family navy; a grey desktop theme can never make
    # these cards grey. GDK_PIXBUF_MODULE_FILE lets the SVG icons load under
    # Xvfb; the app captures its own window, never the desktop.
    env NO_AT_BRIDGE=1 \
        GDK_PIXBUF_MODULE_FILE="${GDK_PIXBUF_MODULE_FILE:-/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/2.10.0/loaders.cache}" \
        XDG_DATA_DIRS="$THEME_SHARE:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" \
        xvfb-run -a python3 "$APP" \
            --fake-data "$FAKE" --capture "$page" --palette "$palette" \
            --out "$SCREENS/$page-$suffix.png"
}

for page in first-run overview roles move drivers; do
    render "$page" dark spaced-dark
    render "$page" light light
done

ls -1 "$SCREENS"/*.png
