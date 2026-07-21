#!/bin/bash
# Emit the package names from the simple list-only YAML configuration.
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

awk '/^[[:space:]]+-[[:space:]]+/ { print $2 }' \
    "$PROJECT_ROOT/config/packages.yaml" | sort -u
