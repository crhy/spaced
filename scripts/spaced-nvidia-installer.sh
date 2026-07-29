#!/bin/bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/root/spaced-nvidia-installer-backup-$STAMP"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    return 1 2>/dev/null || exit 1
fi

mkdir -p "$BACKUP_DIR" /usr/lib/spaced-linux /etc/xdg/autostart /usr/share/applications

for target in \
    /usr/lib/spaced-linux/spaced-nvidia-helper \
    /usr/lib/spaced-linux/spaced-nvidia-installer.py \
    /usr/lib/spaced-linux/spaced-nvidia-postboot.py \
    /usr/share/applications/spaced-nvidia-installer.desktop \
    /etc/xdg/autostart/spaced-nvidia-postboot.desktop; do
    if [ -e "$target" ] || [ -L "$target" ]; then
        cp -a --parents "$target" "$BACKUP_DIR"
    fi
done

install -o root -g root -m 0755 "$SOURCE_DIR/spaced-nvidia-helper" /usr/lib/spaced-linux/spaced-nvidia-helper
install -o root -g root -m 0755 "$SOURCE_DIR/spaced-nvidia-installer.py" /usr/lib/spaced-linux/spaced-nvidia-installer.py
install -o root -g root -m 0755 "$SOURCE_DIR/spaced-nvidia-postboot.py" /usr/lib/spaced-linux/spaced-nvidia-postboot.py
install -o root -g root -m 0644 "$SOURCE_DIR/spaced-nvidia-installer.desktop" /usr/share/applications/spaced-nvidia-installer.desktop
install -o root -g root -m 0644 "$SOURCE_DIR/spaced-nvidia-postboot.desktop" /etc/xdg/autostart/spaced-nvidia-postboot.desktop

cat > /usr/local/bin/spaced-nvidia-installer <<'EOF_LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/spaced-linux/spaced-nvidia-installer.py "$@"
EOF_LAUNCHER
chown root:root /usr/local/bin/spaced-nvidia-installer
chmod 0755 /usr/local/bin/spaced-nvidia-installer

bash -n /usr/lib/spaced-linux/spaced-nvidia-helper
python3 - <<'PY'
from pathlib import Path
for filename in (
    "/usr/lib/spaced-linux/spaced-nvidia-installer.py",
    "/usr/lib/spaced-linux/spaced-nvidia-postboot.py",
):
    source = Path(filename).read_text(encoding="utf-8")
    compile(source, filename, "exec")
print("Spaced NVIDIA installer files passed syntax checks.")
PY

update-desktop-database /usr/share/applications 2>/dev/null || true

echo
echo "Installed hardened Spaced NVIDIA Driver Installer."
echo "Backup: $BACKUP_DIR"
echo "Launch with: spaced-nvidia-installer"
