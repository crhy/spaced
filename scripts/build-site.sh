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

echo "Cloudflare Pages output created at: $DIST"
