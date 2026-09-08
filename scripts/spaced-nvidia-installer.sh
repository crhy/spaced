#!/bin/bash
# Maintainer install from a complete source checkout. End users receive these
# files through the spaced-mate-default-settings package.
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")/../overlays" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/root/spaced-nvidia-installer-backup-$STAMP"
FILES=(
    usr/lib/spaced-linux/spaced-nvidia-helper
    usr/lib/spaced-linux/spaced-nvidia-config.py
    usr/lib/spaced-linux/spaced-nvidia-compat.py
    usr/lib/spaced-linux/spaced_nvidia_state.py
    usr/lib/spaced-linux/spaced-nvidia-installer.py
    usr/lib/spaced-linux/spaced-nvidia-postboot.py
    usr/local/bin/spaced-nvidia-installer
    usr/local/bin/spaced-graphics-report
    usr/share/applications/spaced-nvidia-installer.desktop
    etc/xdg/autostart/spaced-nvidia-postboot.desktop
    usr/share/polkit-1/actions/com.spacedlinux.nvidia.policy
)

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this maintainer installer with sudo from a complete Spaced source checkout." >&2
    exit 1
fi

# Check the complete source before changing any installed file.
for target in "${FILES[@]}"; do
    [ -f "$SOURCE_DIR/$target" ] || { echo "Missing source: $SOURCE_DIR/$target" >&2; exit 1; }
done
bash -n "$SOURCE_DIR/usr/lib/spaced-linux/spaced-nvidia-helper"
python3 - "$SOURCE_DIR" <<'PY_CHECK'
from pathlib import Path
import sys
root = Path(sys.argv[1]) / "usr/lib/spaced-linux"
for name in ("spaced-nvidia-config.py", "spaced-nvidia-compat.py", "spaced_nvidia_state.py",
             "spaced-nvidia-installer.py", "spaced-nvidia-postboot.py"):
    compile((root / name).read_text(), name, "exec")
PY_CHECK

mkdir -p "$BACKUP_DIR"
for target in "${FILES[@]}"; do
    if [ -e "/$target" ] || [ -L "/$target" ]; then
        cp -a --parents "/$target" "$BACKUP_DIR"
    fi
    mode=0644
    case "$target" in
        usr/local/bin/*|usr/lib/spaced-linux/spaced-nvidia-*) mode=0755 ;;
    esac
    install -D -o root -g root -m "$mode" "$SOURCE_DIR/$target" "/$target"
done
update-desktop-database /usr/share/applications 2>/dev/null || true

echo "Installed Spaced Video Drivers application files."
echo "Backup: $BACKUP_DIR"
echo "Launch with: spaced-nvidia-installer"
