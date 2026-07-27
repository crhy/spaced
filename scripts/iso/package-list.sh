#!/bin/bash
# Emit every package from config/packages.yaml, regardless of YAML indentation.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

python3 - "$PROJECT_ROOT/config/packages.yaml" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])

with path.open(encoding="utf-8") as source:
    data = yaml.safe_load(source)

if not isinstance(data, dict):
    raise SystemExit(f"{path}: expected a mapping of package groups")

packages = set()

for group, values in data.items():
    if not isinstance(values, list):
        raise SystemExit(f"{path}: group {group!r} is not a package list")

    for package in values:
        if not isinstance(package, str) or not package.strip():
            raise SystemExit(
                f"{path}: invalid package in group {group!r}: {package!r}"
            )

        packages.add(package.strip())

for package in sorted(packages):
    print(package)
PY
