#!/bin/bash
# Maintainer install from a complete source checkout. End users receive these
# files through the spaced-mate-default-settings package.
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")/../overlays" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/root/spaced-nvidia-installer-backup-$STAMP"
FILES=(
    usr/lib/spaced-linux/spaced_gpu.py
    usr/lib/spaced-linux/spaced-gpu-manager.py
    usr/lib/spaced-linux/spaced-gpu-helper
    usr/local/bin/spaced-gpu-manager
    etc/init.d/spaced-gpu-guard
    etc/xdg/autostart/spaced-gpu-trial.desktop
    usr/share/polkit-1/actions/com.spacedlinux.gpu.policy
    usr/lib/spaced-linux/spaced-nvidia-helper
    usr/lib/spaced-linux/spaced-nvidia-config.py
    usr/lib/spaced-linux/spaced-nvidia-compat.py
    usr/lib/spaced-linux/spaced_nvidia_state.py
    usr/lib/spaced-linux/spaced-nvidia-installer.py
    usr/lib/spaced-linux/spaced-nvidia-postboot.py
    usr/local/bin/spaced-gpu-driver-manager
    usr/local/bin/spaced-nvidia-installer
    usr/local/bin/spaced-graphics-report
    usr/share/applications/spaced-gpu-driver-manager.desktop
    etc/xdg/autostart/spaced-nvidia-postboot.desktop
    usr/share/polkit-1/actions/com.spacedlinux.nvidia.policy
)

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this maintainer installer with sudo from a complete Spaced source checkout." >&2
    exit 1
fi

# Do not replace a running transaction's helper or an active trial's guard.
mkdir -p /var/lib/spaced-nvidia-installer
exec 7>/var/lib/spaced-nvidia-installer/transaction.lock
flock -n 7 || { echo 'Another graphics operation is running.' >&2; exit 1; }
python3 - <<'PY_TRIAL'
import json
from pathlib import Path
path = Path('/var/lib/spaced-gpu-manager/trial.json')
if path.exists() and json.loads(path.read_text()).get('phase') in ('staged', 'trial'):
    raise SystemExit('Confirm or revert the existing desktop trial before installing.')
PY_TRIAL

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
             "spaced-nvidia-installer.py", "spaced-nvidia-postboot.py",
             "spaced_gpu.py", "spaced-gpu-manager.py", "spaced-gpu-helper"):
    compile((root / name).read_text(), name, "exec")
PY_CHECK

mkdir -p "$BACKUP_DIR"
for target in "${FILES[@]}"; do
    if [ -e "/$target" ] || [ -L "/$target" ]; then
        cp -a --parents "/$target" "$BACKUP_DIR"
    fi
    mode=0644
    case "$target" in
        usr/local/bin/*|usr/lib/spaced-linux/spaced-nvidia-*|usr/lib/spaced-linux/spaced-gpu-*|etc/init.d/*) mode=0755 ;;
    esac
    install -D -o root -g root -m "$mode" "$SOURCE_DIR/$target" "/$target"
done
update-desktop-database /usr/share/applications 2>/dev/null || true
update-rc.d spaced-gpu-guard defaults
rm -f /usr/share/applications/spaced-nvidia-installer.desktop

echo "Installed Spaced GPU Manager application files. Graphics configuration is unchanged."
echo "Backup: $BACKUP_DIR"
echo "Launch with: spaced-gpu-manager"
