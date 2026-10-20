#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
ASSETS="$DIST/assets"

rm -rf "$DIST"
mkdir -p "$ASSETS"

cp "$ROOT/website/index.html" "$DIST/index.html"
cp "$ROOT/website/themes.html" "$DIST/themes.html"
cp "$ROOT/website/help.html" "$DIST/help.html"
cp "$ROOT/website/styles.css" "$DIST/styles.css"
cp "$ROOT/website/script.js" "$DIST/script.js"
cp "$ROOT/website/_headers" "$DIST/_headers"

cp -a "$ROOT/website/assets/." "$ASSETS/"
cp "$ROOT/branding/spaced-icon-fancy.png" "$ASSETS/spaced-icon-fancy.png"
cp "$ROOT/overlays/usr/share/backgrounds/spaced/spaced-orbit-4k.jpg" "$ASSETS/spaced-orbit-4k.jpg"
cp "$ROOT/overlays/usr/share/backgrounds/spaced/solarsystem.jpg" "$ASSETS/solarsystem.jpg"
cp "$ROOT/overlays/usr/share/backgrounds/spaced/euclidgalacticcore.jpg" "$ASSETS/euclidgalacticcore.jpg"

echo "Cloudflare Pages output created at: $DIST"
