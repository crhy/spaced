#!/bin/bash
set -euo pipefail

for remote in flathub spaced-github; do
    descriptor="/usr/share/flatpak/remotes.d/$remote.flatpakrepo"
    [ -s "$descriptor" ] || {
        echo "Missing signed Flatpak descriptor: $descriptor" >&2
        exit 1
    }
    /usr/bin/flatpak remote-add --system --if-not-exists "$remote" "$descriptor"
done

# Do not install the catalog itself in the live image. User applications are
# selected only after Calamares has completed, keeping the ISO lean and making
# installation state explicit.
# Upstream binaries are fixed through versioned source packages, never opaque
# in-place byte patches in this hook.
