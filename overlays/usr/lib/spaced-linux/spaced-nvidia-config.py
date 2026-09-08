#!/usr/bin/python3
"""Back up only graphics files touched by a driver transaction.

Rollback restores a file only when it still matches the installer's recorded
result. Later administrator edits and unrelated files are preserved.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import stat
import tempfile


WRITTEN_PATHS = (
    "etc/default/grub", "etc/initramfs-tools/modules",
    "etc/modprobe.d/zz-spaced-nvidia.conf",
    "etc/dconf/db/local.d/00-spaced-compiz",
)
FIXED_PATHS = (*WRITTEN_PATHS, "etc/modprobe.d/spaced-live-nvidia.conf", "etc/X11/xorg.conf")
FIXED_PATHS += (
    "etc/apt/sources.list.d/cuda-debian12-x86_64.list",
    "etc/apt/sources.list.d/cuda-debian13-x86_64.list",
    "usr/share/keyrings/cuda-archive-keyring.gpg",
)


def snapshot(path):
    if path.is_symlink():
        return {"type": "symlink", "target": os.readlink(path)}
    if not path.exists():
        return {"type": "missing"}
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Expected a graphics configuration file: {path}")
    return {"type": "file", "data": base64.b64encode(path.read_bytes()).decode(),
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}


def write_manifest(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".config-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as target:
            json.dump(payload, target, sort_keys=True)
            target.flush()
            os.fsync(target.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def backup(root, manifest):
    paths = set(FIXED_PATHS)
    for path in (root / "etc/modprobe.d").glob("*"):
        if path.is_file() or path.is_symlink():
            paths.add(path.relative_to(root).as_posix())
    for path in (root / "etc/X11/xorg.conf.d").glob("*"):
        if any(name in path.name.lower() for name in ("nvidia", "nouveau")):
            if path.is_file() or path.is_symlink():
                paths.add(path.relative_to(root).as_posix())
    for name in WRITTEN_PATHS:
        if (root / name).is_symlink():
            raise ValueError(f"Refusing to overwrite a linked graphics configuration: /{name}")
    write_manifest(manifest, {"version": 1, "before": {
        name: snapshot(root / name) for name in sorted(paths)
    }})


def load_manifest(manifest):
    payload = json.loads(manifest.read_text())
    if payload.get("version") != 1 or not isinstance(payload.get("before"), dict):
        raise ValueError("Unsupported graphics backup; manual recovery is required")
    for name in payload["before"]:
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Invalid path in graphics backup")
    return payload


def capture(root, manifest):
    payload = load_manifest(manifest)
    payload["after"] = {name: snapshot(root / name) for name in payload["before"]}
    write_manifest(manifest, payload)


def restore(root, manifest):
    payload = load_manifest(manifest)
    if "after" not in payload:
        raise ValueError("No completed graphics change record; manual recovery is required")
    failed = []
    for name, before in payload["before"].items():
        after = payload["after"].get(name)
        if after == before:
            continue
        path = root / name
        try:
            current = snapshot(path)
            if current == before:
                continue  # A previous recovery already restored this file.
            if current != after:
                raise ValueError("changed since driver installation; preserving it")
            if before["type"] == "missing":
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                if before["type"] == "symlink":
                    path.unlink(missing_ok=True)
                    path.symlink_to(before["target"])
                else:
                    if path.is_symlink():
                        path.unlink()
                    path.write_bytes(base64.b64decode(before["data"], validate=True))
                    path.chmod(before["mode"])
                    if os.geteuid() == 0:
                        os.chown(path, before["uid"], before["gid"])
        except (OSError, ValueError) as error:
            failed.append(name)
            print(f"Cannot restore /{name}: {error}")
    return not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "capture", "restore"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path("/"))
    args = parser.parse_args()
    try:
        result = globals()[args.action](args.root, args.manifest)
    except (OSError, ValueError, KeyError) as error:
        print(f"Graphics configuration recovery: {error}")
        return 52
    return 52 if result is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
