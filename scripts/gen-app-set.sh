#!/bin/bash
# Spaced issue #417: the migration report needs a copy of the application set
# that survives on a live system. config/packages.yaml is build-side only, so
# this generator flattens the application groups into a shipped file
# (overlays/usr/share/spaced-linux/app-set.txt) and scripts/check.sh refuses a
# stale copy, the same way it refuses an empty scripts/iso/package-list.sh output.
#
# Usage: scripts/gen-app-set.sh [OUTPUT]   ("-" writes to stdout)
# Output: one entry per line, "<name>\t<apt|flatpak>", sorted.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT=${1:-"$PROJECT_ROOT/overlays/usr/share/spaced-linux/app-set.txt"}

generate() {
    python3 - "$PROJECT_ROOT/config/packages.yaml" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])

with path.open(encoding="utf-8") as source:
    data = yaml.safe_load(source)

if not isinstance(data, dict):
    raise SystemExit(f"{path}: expected a mapping of package groups")

# apt: the application packages Spaced installs natively.
# flatpak: the Flatpak side of the application set, reinstalled from Flathub.
groups = (("applications", "apt"), ("file_managers", "apt"), ("flatpak", "flatpak"))
for group, _channel in groups:
    if group not in data:
        raise SystemExit(f"{path}: missing application group {group!r}")

entries = {}
for group, channel in groups:
    values = data[group]
    if not isinstance(values, list):
        raise SystemExit(f"{path}: group {group!r} is not a package list")

    for package in values:
        if not isinstance(package, str) or not package.strip():
            raise SystemExit(
                f"{path}: invalid package in group {group!r}: {package!r}"
            )

        name = package.strip()
        if name in entries and entries[name] != channel:
            raise SystemExit(f"{path}: {name!r} is requested through two channels")

        entries[name] = channel

for name in sorted(entries):
    print(f"{name}\t{entries[name]}")
PY
}

if [ "$OUTPUT" = "-" ]; then
    generate
else
    mkdir -p "$(dirname "$OUTPUT")"
    generate > "$OUTPUT"
fi
