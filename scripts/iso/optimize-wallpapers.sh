#!/bin/bash
# Run only when preparing a new spaced-wallpapers package revision.
# Original artwork is retained in SpacedLinuxWallpapers/ and Git history.
set -euo pipefail
cd "$(dirname "$0")/../.."
export MAGICK_THREAD_LIMIT=2
wallpapers=overlays/usr/share/backgrounds/spaced
for source in "$wallpapers"/*.jpg; do
    magick "$source" -resize '2560x2560>' -strip -quality 90 "$source"
done
for name in spaced-orbit-4k euclid-galaxy-garland; do
    [ ! -L "$wallpapers/$name.png" ] || continue
    magick "$wallpapers/$name.png" -resize '2560x2560>' -strip -quality 90 "$wallpapers/$name.jpg"
    rm "$wallpapers/$name.png"
    # Preserve wallpaper selections in existing user profiles.
    ln -s "$name.jpg" "$wallpapers/$name.png"
done
for name in SpacedBack SpacedBackLight; do
    rm "$wallpapers/$name.png"
    ln -s "$name.jpg" "$wallpapers/$name.png"
done
