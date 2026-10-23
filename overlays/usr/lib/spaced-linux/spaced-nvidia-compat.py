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
from functools import cmp_to_key


def check_hardware(database, sys_path, allowed_legacy=()):
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
            if chip.get("legacybranch") and chip["legacybranch"] not in allowed_legacy:
                raise ValueError(
                    f"{chip['name']} [10de:{device_id:04x}] requires NVIDIA's legacy {chip['legacybranch']} branch. "
                    "The current repository driver is incompatible. Keep the current driver; this installer does not replace it with an unsupported branch.")
        branch = matches[0].get("legacybranch")
        branch_note = f" (legacy {branch})" if branch else ""
        print(f"Supported NVIDIA device: {matches[0]['name']} [10de:{device_id:04x}]{branch_note}")
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


def debian_version_key():
    """Return a sort key implementing Debian's version comparison.

    Epoch ``N:`` is compared numerically; the upstream part and the ``-revision``
    part are compared run by run, with digit runs compared numerically and
    non-digit runs compared character by character where ``~`` sorts before every
    other character (including the end of the string).
    """

    def parse(version):
        epoch = 0
        rest = version
        match = re.match(r"(\d+):(.*)", version)
        if match:
            epoch = int(match.group(1))
            rest = match.group(2)
        if "-" in rest:
            upstream, revision = rest.rsplit("-", 1)
        else:
            upstream, revision = rest, ""
        return epoch, upstream, revision

    def char_rank(char):
        # dpkg order: "~" first, then the end of the part, then letters,
        # then every other character.
        if char == "~":
            return -1
        if char == "":
            return 0
        return ord(char) if char.isalpha() else ord(char) + 256

    def compare_part(left, right):
        i = j = 0
        while i < len(left) or j < len(right):
            lc = left[i] if i < len(left) else ""
            rc = right[j] if j < len(right) else ""
            if lc.isdigit() and rc.isdigit():
                i_end = i
                while i_end < len(left) and left[i_end].isdigit():
                    i_end += 1
                j_end = j
                while j_end < len(right) and right[j_end].isdigit():
                    j_end += 1
                left_value = int(left[i:i_end])
                right_value = int(right[j:j_end])
                if left_value != right_value:
                    return -1 if left_value < right_value else 1
                i, j = i_end, j_end
            else:
                left_rank, right_rank = char_rank(lc), char_rank(rc)
                if left_rank != right_rank:
                    return -1 if left_rank < right_rank else 1
                i += 1
                j += 1
        return 0

    def compare(left, right):
        left_epoch, left_upstream, left_revision = parse(left)
        right_epoch, right_upstream, right_revision = parse(right)
        if left_epoch != right_epoch:
            return -1 if left_epoch < right_epoch else 1
        upstream_order = compare_part(left_upstream, right_upstream)
        if upstream_order:
            return upstream_order
        return compare_part(left_revision, right_revision)

    return cmp_to_key(compare)


def legacy_version(madison_output, max_major):
    candidates = []
    for line in madison_output.splitlines():
        fields = line.split("|")
        if len(fields) < 3:
            continue
        if "developer.download.nvidia.com" in fields[2]:
            continue
        version = fields[1].strip()
        if not version:
            continue
        leading = re.match(r"\d+", version.split(":", 1)[-1])
        if not leading or int(leading.group(0)) > max_major:
            continue
        candidates.append(version)
    if not candidates:
        raise ValueError(f"No Devuan nvidia-driver at or below the {max_major} branch is available.")
    return max(candidates, key=debian_version_key())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("hardware", "recommendation", "legacy-version"))
    parser.add_argument("recommendation", nargs="?", type=Path)
    parser.add_argument("--database", type=Path, default=Path("/usr/share/nvidia-driver-assistant/supported-gpus/supported-gpus.json"))
    parser.add_argument("--sys-path", type=Path, default=Path("/sys"))
    parser.add_argument("--allow-legacy", action="append", default=[],
                        help="legacy branch supplied by a separately verified package source")
    parser.add_argument("--max-major", type=int, default=580,
                        help="highest NVIDIA branch major version to accept for a legacy GPU")
    args = parser.parse_args()
    try:
        if args.action == "hardware":
            check_hardware(args.database, args.sys_path, args.allow_legacy)
        elif args.action == "legacy-version":
            if args.recommendation is None:
                raise ValueError("Missing NVIDIA madison output file.")
            print(legacy_version(args.recommendation.read_text(), args.max_major))
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
