#!/usr/bin/env bash
# Measure the clickable area of the close / maximize / minimize buttons of a Spaced theme (issue #279).
# Runs Marco with the theme on a virtual screen and clicks across the title bar; never touches the real desktop.
# Usage: scripts/tests/titlebar-hit-test.sh [theme ...]     (default: every theme in overlays/usr/share/themes)
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
themes_dir="$repo_root/overlays/usr/share/themes"
if [ "$#" -eq 0 ]; then mapfile -t themes < <(cd "$themes_dir" && ls -d */metacity-1 | cut -d/ -f1); else themes=("$@"); fi
for theme in "${themes[@]}"; do
    work="$(mktemp -d /tmp/spaced-hit-test.XXXXXX)"
    mkdir -p "$work/home/.themes" "$work/config/glib-2.0/settings"
    cp -r "$themes_dir/$theme" "$work/home/.themes/"
    printf '[org/mate/marco/general]\ntheme=%s\n' "'$theme'" > "$work/config/glib-2.0/settings/keyfile"
    HOME="$work/home" XDG_CONFIG_HOME="$work/config" GSETTINGS_BACKEND=keyfile THEME="$theme" \
        xvfb-run -a -s "-screen 0 1280x800x24" python3 "$repo_root/scripts/tests/titlebar_hit_test.py" || true
    rm -rf "$work"
done
