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
cp "$ROOT/website/benchmarks.js" "$DIST/benchmarks.js"
cp "$ROOT/website/_headers" "$DIST/_headers"

cp -a "$ROOT/website/assets/." "$ASSETS/"

# Keep the benchmarks JSON in step with its CSV evidence (skips silently when the
# evidence drive is not mounted; the committed JSON is then used as-is).
if [ -f /media/rhy/data/bench-evidence/showdown-20261122/system.csv ]; then
  python3 "$ROOT/scripts/vm/bench/export-site.py" --out "$ASSETS/bench/showdown-2026-11-22.json"
fi

echo "Cloudflare Pages output created at: $DIST"
