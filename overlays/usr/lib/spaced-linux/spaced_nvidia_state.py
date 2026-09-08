"""Read-only NVIDIA installation state shared by the GTK tools."""
import hashlib
from pathlib import Path

PENDING = Path("/var/lib/spaced-nvidia-installer/reboot-required")


def marker_id(pending=PENDING):
    return hashlib.sha256(pending.read_bytes()).hexdigest()[:20]


def ack_path(pending=PENDING):
    return Path.home() / ".cache/spaced-nvidia-installer" / f"verified-{marker_id(pending)}"


def installation_verified(pending=PENDING):
    try:
        return pending.is_file() and ack_path(pending).is_file()
    except OSError:
        return False


def awaiting_reboot(pending=PENDING, boot_id_path=Path("/proc/sys/kernel/random/boot_id")):
    try:
        values = dict(line.split("=", 1) for line in pending.read_text().splitlines() if "=" in line)
        installed_boot = values.get("boot_id")
        if installed_boot:
            return installed_boot == boot_id_path.read_text().strip()
        # Older installers omitted the boot ID. Preserve their original
        # verify-on-login behavior instead of waiting forever for missing data.
        return False
    except OSError:
        return False
