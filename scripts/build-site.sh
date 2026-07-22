#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
ASSETS="$DIST/assets"

rm -rf "$DIST"
mkdir -p "$ASSETS"

cp "$ROOT/website/index.html" "$DIST/index.html"
cp "$ROOT/website/styles.css" "$DIST/styles.css"
cp "$ROOT/website/script.js" "$DIST/script.js"
cp "$ROOT/website/_headers" "$DIST/_headers"

cp "$ROOT/overlays/usr/share/pixmaps/spaced-logo.png" "$ASSETS/spaced-logo.png"
cp "$ROOT/SpacedLinuxWallpapers/spaced-orbit-4k.png" "$ASSETS/spaced-orbit-4k.png"
cp "$ROOT/SpacedLinuxWallpapers/SpacedBack.png" "$ASSETS/SpacedBack.png"
cp "$ROOT/SpacedLinuxWallpapers/winxp.jpg" "$ASSETS/winxp.jpg"
cp "$ROOT/SpacedLinuxWallpapers/macos.jpg" "$ASSETS/macos.jpg"
cp "$ROOT/SpacedLinuxWallpapers/android.jpg" "$ASSETS/android.jpg"
cp "$ROOT/SpacedLinuxWallpapers/bluecanvas.jpg" "$ASSETS/bluecanvas.jpg"
cp "$ROOT/SpacedLinuxWallpapers/solarsystem.jpg" "$ASSETS/solarsystem.jpg"
cp "$ROOT/SpacedLinuxWallpapers/euclidgalacticcore.jpg" "$ASSETS/euclidgalacticcore.jpg"

echo "Cloudflare Pages output created at: $DIST"
