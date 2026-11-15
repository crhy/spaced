#!/usr/bin/env python3
"""Guarantee the installed fstab and crypttab match the final partition plan.

Issue #413: a planned separate /home must appear in the installed fstab.
Issue #420: every planned LUKS volume must appear in the installed crypttab
naming the boot keyfile, or the installed initramfs has nothing to unlock and
the system drops to an (initramfs) shell on first boot.
"""

import os

import libcalamares


FS_MAP = {
    "fat16": "vfat",
    "fat32": "vfat",
    "linuxswap": "swap",
}

# luksbootkeyfile writes this on the installer, fstab copies it into the target
# and initramfscfg packs it into the initramfs (KEYFILE_PATTERN). The cryptroot
# hook only unlocks a volume whose crypttab line names it.
KEYFILE = "/crypto_keyfile.bin"


def pretty_name():
    return "Verifying the partition plan."


def _error(detail, title="Partition configuration error", untouched="the existing home partition"):
    libcalamares.utils.warning(detail)
    return (
        title,
        detail + " The installation has stopped without changing {}.".format(untouched),
    )


def _fstab_mounts(path):
    mounts = set()
    with open(path, encoding="utf-8") as fstab:
        for raw_line in fstab:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) >= 2:
                mounts.add(fields[1])
    return mounts


def _device(partition):
    mapper = partition.get("luksMapperName")
    if mapper:
        return "/dev/mapper/" + mapper
    uuid = partition.get("uuid")
    if uuid:
        return "UUID=" + uuid
    return partition.get("device")


def _luks_partitions(partitions):
    return [p for p in partitions if p.get("luksMapperName")]


def _crypttab_source(partition):
    """Identify the encrypted container itself, not the filesystem inside it."""
    for key in ("luksUuid", "partUuid", "uuid"):
        value = partition.get(key)
        if value:
            return "UUID=" + value
    return partition.get("device") or None


def _crypttab_mappers(path):
    mappers = set()
    if not os.path.isfile(path):
        return mappers
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line and not line.startswith("#"):
                mappers.add(line.split()[0])
    return mappers


def _ensure_boot_keyfile(root, source=KEYFILE):
    """The target must own the keyfile before update-initramfs packs it."""
    target = os.path.join(root, KEYFILE.lstrip("/"))
    if os.path.isfile(target):
        return True
    if not os.path.isfile(source):
        return False
    with open(source, "rb") as handle, open(target, "wb") as destination:
        destination.write(handle.read())
    os.chmod(target, 0o400)
    return True


def _ensure_crypttab(root, partitions):
    """Add only the crypttab lines the final plan requires and Calamares lost."""
    luks = _luks_partitions(partitions)
    if not luks:
        return None

    planned = {}
    for partition in luks:
        mapper = partition["luksMapperName"]
        source = _crypttab_source(partition)
        if not source:
            return _error(
                "The encrypted volume {} has no usable LUKS identifier, so the "
                "installed system could never unlock it.".format(mapper),
                untouched="the existing crypttab",
            )
        planned[mapper] = source

    path = os.path.join(root, "etc", "crypttab")
    missing = [m for m in planned if m not in _crypttab_mappers(path)]
    if not missing:
        return None
    if not _ensure_boot_keyfile(root):
        # Not fatal: cryptroot falls back to asking for the passphrase at boot,
        # which is still a bootable system, unlike a missing crypttab entry.
        libcalamares.utils.warning(
            "No {} in the installed system, so the encrypted volumes will ask "
            "for their passphrase at boot.".format(KEYFILE)
        )

    needs_newline = os.path.isfile(path) and os.path.getsize(path)
    if needs_newline:
        with open(path, "rb") as existing:
            existing.seek(-1, os.SEEK_END)
            needs_newline = existing.read(1) != b"\n"

    with open(path, "a", encoding="utf-8") as crypttab:
        if needs_newline:
            crypttab.write("\n")
        for mapper in missing:
            # Calamares' own field widths, keyfile auth, "luks" options.
            crypttab.write("{:<41} {:<38} {:<20} luks\n".format(
                mapper, planned[mapper], KEYFILE
            ))
        crypttab.flush()
        os.fsync(crypttab.fileno())

    libcalamares.utils.debug(
        "Repaired a missing crypttab entry for: {}".format(", ".join(missing))
    )
    return None


def _append_home(path, partition):
    source = _device(partition)
    filesystem = FS_MAP.get(partition.get("fs", "").lower(), partition.get("fs", "").lower())
    if not source or not filesystem:
        return False

    # Match Spaced's Calamares fstab default. Calamares normally writes this
    # line itself; this repair is deliberately limited to the exact /home plan.
    line = "{:<41} {:<14} {:<7} {:<10} 0 2\n".format(
        source, "/home", filesystem, "defaults,noatime"
    )
    needs_newline = False
    if os.path.getsize(path):
        with open(path, "rb") as existing:
            existing.seek(-1, os.SEEK_END)
            needs_newline = existing.read(1) != b"\n"

    with open(path, "a", encoding="utf-8") as fstab:
        if needs_newline:
            fstab.write("\n")
        fstab.write(line)
        fstab.flush()
        os.fsync(fstab.fileno())
    return True


def run():
    storage = libcalamares.globalstorage
    partitions = storage.value("partitions") or []
    reuse_home = bool(storage.value("reuseHome"))
    homes = [p for p in partitions if p.get("mountPoint") == "/home"]

    if reuse_home and not homes:
        return _error(
            "Calamares promised to reuse a home partition, but the final partition plan lost it."
        )
    if len(homes) > 1:
        return _error("The final partition plan contains more than one /home partition.")

    root = storage.value("rootMountPoint")
    if not root:
        return _error("Calamares did not provide the target system mount point.")

    crypttab_error = _ensure_crypttab(root, partitions)

    if not homes:
        return crypttab_error

    home = homes[0]
    if home.get("fs", "").lower() == "zfs":
        return crypttab_error

    fstab_path = os.path.join(root, "etc", "fstab")
    if not os.path.isfile(fstab_path):
        return crypttab_error or _error("Calamares did not create the target system's /etc/fstab.")

    try:
        if "/home" in _fstab_mounts(fstab_path):
            return crypttab_error
        if not _append_home(fstab_path, home):
            return _error("The planned /home partition has no usable filesystem identifier.")
    except OSError as error:
        return _error("The /home fstab entry could not be verified: {}.".format(error))

    libcalamares.utils.debug(
        "Repaired a missing /home entry in the target system's /etc/fstab."
    )
    return crypttab_error
