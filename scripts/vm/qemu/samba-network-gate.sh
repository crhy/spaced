#!/bin/bash
# Compatibility entry point; use network-services-gate.sh for new automation.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "$script_dir/network-services-gate.sh" "$@"
