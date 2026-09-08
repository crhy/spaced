#!/usr/bin/python3
"""Validate NVIDIA's hardware database and printed package recommendation.

The upstream assistant chooses a module flavour, but does not reject every
legacy GPU and does not propagate a failed --install command's exit status.
Spaced therefore queries it and executes only a validated APT package name.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import sys


def check_hardware(database, sys_path):
    chips = json.loads(database.read_text())["chips"]
    found = 0
    for device in sorted((sys_path / "bus/pci/devices").glob("*")):
        if int((device / "vendor").read_text(), 16) != 0x10DE:
            continue
        if int((device / "class").read_text(), 16) >> 16 != 0x03:
            continue
        found += 1
        device_id = int((device / "device").read_text(), 16)
        subsystem = {
            "subvendorid": int((device / "subsystem_vendor").read_text(), 16),
            "subdevid": int((device / "subsystem_device").read_text(), 16),
        }
        matches = [chip for chip in chips if int(chip["devid"], 16) == device_id
                   and all(key not in chip or int(chip[key], 16) == value
                           for key, value in subsystem.items())]
        if not matches:
            raise ValueError(f"NVIDIA PCI device 10de:{device_id:04x} is absent from the installed support database; keep the current driver.")
        # Prefer subsystem-specific entries over a generic device entry.
        specificity = max(sum(key in chip for key in subsystem) for chip in matches)
        matches = [chip for chip in matches if sum(key in chip for key in subsystem) == specificity]
        for chip in matches:
            if chip.get("legacybranch"):
                raise ValueError(
                    f"{chip['name']} [10de:{device_id:04x}] requires NVIDIA's legacy {chip['legacybranch']} branch. "
                    "The current repository driver is incompatible. Keep the current driver; this installer does not replace it with an unsupported branch.")
        print(f"Supported NVIDIA device: {matches[0]['name']} [10de:{device_id:04x}]")
    if not found:
        raise ValueError("No NVIDIA display device was found in sysfs.")


def recommended_package(output):
    packages = []
    for line in output.splitlines():
        if not re.match(r"\s*(?:sudo\s+)?apt(?:-get)?\s", line):
            continue
        words = shlex.split(line)
        if words[0] == "sudo":
            words.pop(0)
        if len(words) < 3 or words[1] != "install":
            raise ValueError("Unexpected NVIDIA package instruction.")
        arguments = [word for word in words[2:] if word not in ("-y", "-V", "-Vy", "-yV", "--yes", "--assume-yes")]
        if len(arguments) != 1 or not re.fullmatch(r"(?:nvidia-open|cuda-drivers)(?:-[0-9]+)?", arguments[0]):
            raise ValueError("Unexpected NVIDIA driver package; no command was executed.")
        packages.append(arguments[0])
    if len(packages) != 1:
        raise ValueError("NVIDIA did not provide exactly one supported driver package instruction.")
    return packages[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("hardware", "recommendation"))
    parser.add_argument("recommendation", nargs="?", type=Path)
    parser.add_argument("--database", type=Path, default=Path("/usr/share/nvidia-driver-assistant/supported-gpus/supported-gpus.json"))
    parser.add_argument("--sys-path", type=Path, default=Path("/sys"))
    args = parser.parse_args()
    try:
        if args.action == "hardware":
            check_hardware(args.database, args.sys_path)
        else:
            if args.recommendation is None:
                raise ValueError("Missing NVIDIA recommendation file.")
            print(recommended_package(args.recommendation.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"NVIDIA compatibility: {error}", file=sys.stderr)
        return 24
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
