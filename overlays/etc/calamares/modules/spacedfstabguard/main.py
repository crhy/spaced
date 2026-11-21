#!/usr/bin/env python3
"""Guarantee that Calamares keeps a planned separate /home in fstab."""

import os
import re

import libcalamares


FS_MAP = {
    "fat16": "vfat",
    "fat32": "vfat",
    "linuxswap": "swap",
}


def pretty_name():
    return "Verifying the home partition."


def _error(detail):
    libcalamares.utils.warning(detail)
    return (
        "Home partition configuration error",
        detail + " The installation has stopped without changing the existing home partition.",
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


def _ensure_encrypted_root(root, partitions):
    """Debian initramfs-tools needs the root mapping in the target crypttab.

    Only luksUuid identifies the outer container. Never substitute the inner
    filesystem UUID or GPT PARTUUID. Missing metadata is an installer error,
    not a reason to guess a device which might become unbootable.
    """
    encrypted = [p for p in partitions
                 if p.get("mountPoint") == "/" and p.get("luksMapperName")]
    if not encrypted:
        return None

    def fail(detail):
        libcalamares.utils.warning(detail)
        return ("Encrypted root configuration error", detail)

    if len(encrypted) != 1 or not root:
        return fail("The encrypted root partition plan is incomplete or ambiguous.")
    partition = encrypted[0]
    mapper, uuid = partition["luksMapperName"], partition.get("luksUuid", "")
    if not re.fullmatch(r"[A-Za-z0-9_+.-]+", mapper) or not re.fullmatch(
            r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}", uuid):
        return fail("The encrypted root has no valid mapper name or LUKS UUID.")
    path = os.path.join(root, "etc", "crypttab")
    try:
        if os.path.islink(path):
            return fail("The installed crypttab must not be a symbolic link.")
        text = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        entries = [line.split() for line in text.splitlines()
                   if line.strip() and not line.lstrip().startswith("#")]
        matches = [fields for fields in entries if fields[0] == mapper]
        if matches:
            if len(matches) != 1 or len(matches[0]) < 3 or matches[0][1] != "UUID=" + uuid:
                return fail("The installed encrypted root mapping conflicts with the partition plan.")
            key = matches[0][2]
            if key not in ("none", "-"):
                key_path = os.path.join(root, key.lstrip("/"))
                if key != "/crypto_keyfile.bin" or os.path.islink(key_path) or not os.path.isfile(key_path):
                    return fail("The encrypted root crypttab references an unavailable or unsupported keyfile.")
                os.chmod(key_path, 0o400)
            return None
        # Repair only a missing mapping. A passphrase prompt is safe even when
        # a keyfile exists: its presence alone does not prove an enrolled keyslot.
        with open(path, "a", encoding="utf-8") as handle:
            if text and not text.endswith("\n"):
                handle.write("\n")
            handle.write("{} UUID={} none luks\n".format(mapper, uuid))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        return fail("Cannot verify the encrypted root crypttab: {}".format(error))
    return None


def run():
    storage = libcalamares.globalstorage
    partitions = storage.value("partitions") or []
    reuse_home = bool(storage.value("reuseHome"))
    homes = [p for p in partitions if p.get("mountPoint") == "/home"]

    encryption_error = _ensure_encrypted_root(storage.value("rootMountPoint"), partitions)
    if encryption_error:
        return encryption_error

    if reuse_home and not homes:
        return _error(
            "Calamares promised to reuse a home partition, but the final partition plan lost it."
        )
    if not homes:
        return None
    if len(homes) != 1:
        return _error("The final partition plan contains more than one /home partition.")

    home = homes[0]
    if home.get("fs", "").lower() == "zfs":
        return None

    root = storage.value("rootMountPoint")
    if not root:
        return _error("Calamares did not provide the target system mount point.")
    fstab_path = os.path.join(root, "etc", "fstab")
    if not os.path.isfile(fstab_path):
        return _error("Calamares did not create the target system's /etc/fstab.")

    try:
        if "/home" in _fstab_mounts(fstab_path):
            return None
        if not _append_home(fstab_path, home):
            return _error("The planned /home partition has no usable filesystem identifier.")
    except OSError as error:
        return _error("The /home fstab entry could not be verified: {}.".format(error))

    libcalamares.utils.debug(
        "Repaired a missing /home entry in the target system's /etc/fstab."
    )
    return None
