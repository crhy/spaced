#!/bin/bash
# Emit the package set for the opt-in Xlibre display-server test image (issue #314).
#
# The default image is untouched: scripts/iso/package-list.sh reads
# config/packages.yaml only, and this script reads config/xlibre-test-image.yaml
# only. It refuses to print anything while any entry is still UNRELEASED or
# missing a 64-hex SHA-256, so a half-pinned Xlibre set can never reach an image.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CONFIG=${SPACED_XLIBRE_IMAGE_CONFIG:-$ROOT/config/xlibre-test-image.yaml}

die() {
    printf 'xlibre-package-list: %s\n' "$*" >&2
    exit 1
}

[[ -r $CONFIG ]] || die "cannot read opt-in configuration: $CONFIG"

python3 - "$CONFIG" <<'PY'
from pathlib import Path
import re
import sys
import yaml

path = Path(sys.argv[1])

with path.open(encoding="utf-8") as source:
    data = yaml.safe_load(source)

if not isinstance(data, dict):
    raise SystemExit(f"{path}: expected a mapping of opt-in image sections")


def section(key):
    if key not in data:
        raise SystemExit(f"{path}: missing {key}")
    return data[key]


def fail(message):
    print(f"xlibre-package-list: {message}", file=sys.stderr)
    raise SystemExit(1)


if section("fallback_boot") != "xorg":
    fail("fallback_boot must stay xorg: the Xorg fallback path is not optional")

replaced = section("replaces")
if not isinstance(replaced, list) or not replaced:
    raise SystemExit(f"{path}: replaces must be a non-empty package list")
for package in replaced:
    if not isinstance(package, str) or not re.fullmatch(
            r"xserver-xorg-[a-z0-9.+-]+", package.strip()):
        raise SystemExit(
            f"{path}: replaces may only name xserver-xorg-* packages, got {package!r}"
        )
replaced = {package.strip() for package in replaced}

matrix = section("matrix")
if not isinstance(matrix, dict) or not matrix:
    raise SystemExit(f"{path}: matrix must be a non-empty mapping of test rows")
for row, value in matrix.items():
    if not isinstance(value, dict) or "result" not in value:
        raise SystemExit(f"{path}: matrix row {row!r} has no result")

entries = section("display_server")
if not isinstance(entries, list) or not entries:
    raise SystemExit(f"{path}: display_server must be a non-empty package list")

packages = []
unpinned = []

for entry in entries:
    if not isinstance(entry, dict):
        raise SystemExit(f"{path}: invalid display_server entry: {entry!r}")

    package = entry.get("package")
    if not isinstance(package, str) or not package.strip():
        raise SystemExit(f"{path}: invalid display_server package name: {package!r}")
    package = package.strip()
    packages.append(package)

    version = entry.get("version")
    sha256 = entry.get("sha256")

    reasons = []
    if not isinstance(version, str) or not version.strip() \
            or version.strip() == "UNRELEASED":
        reasons.append("version is UNRELEASED")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256.strip()):
        reasons.append("sha256 is not a 64-character hex digest")

    if reasons:
        unpinned.append(f"{package} ({', '.join(reasons)})")

fallback = section("fallback_packages")
if not isinstance(fallback, list) or not fallback:
    raise SystemExit(f"{path}: fallback_packages must be a non-empty package list")
for package in fallback:
    if not isinstance(package, str) or not package.strip():
        raise SystemExit(f"{path}: invalid fallback package name: {package!r}")
    if package.strip() in replaced:
        raise SystemExit(
            f"{path}: fallback package {package.strip()!r} is also replaced, "
            "so the Xorg rollback entry would be dropped"
        )

if unpinned:
    fail(
        "refusing the opt-in Xlibre set: every entry must carry a released version "
        f"and a 64-hex SHA-256 verified against https://deb.xlibre.org. Unpinned: "
        + "; ".join(unpinned)
    )

emitted = {package for package in packages + [p.strip() for p in fallback]
           if package.strip() not in replaced}

for package in sorted(emitted):
    print(package)
PY
