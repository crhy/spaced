#!/bin/bash
# Run only when preparing a new spaced-wallpapers package revision.
# Canonical shipped artwork lives only in overlays/usr/share/backgrounds/spaced.
# Full-resolution source history remains available in Git.
set -euo pipefail
cd "$(dirname "$0")/../.."
export MAGICK_THREAD_LIMIT=2
wallpapers=overlays/usr/share/backgrounds/spaced
for source in "$wallpapers"/*.jpg; do
    magick "$source" -resize '2560x2560>' -strip -quality 90 "$source"
done
# Preserve wallpaper selections in existing user profiles without duplicating
# image bytes in the ISO payload.
for name in spaced-orbit-4k euclid-galaxy-garland SpacedBack SpacedBackLight; do
    ln -sfn "$name.jpg" "$wallpapers/$name.png"
done
