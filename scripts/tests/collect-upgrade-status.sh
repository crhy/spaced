#!/bin/bash
# Read only dpkg status directly from each ISO's embedded SquashFS image.
set -euo pipefail
ISO_DIR=${1:?Usage: collect-upgrade-status.sh ISO_DIRECTORY OUTPUT_DIRECTORY}
OUT=${2:?Usage: collect-upgrade-status.sh ISO_DIRECTORY OUTPUT_DIRECTORY}
mkdir -p "$OUT"
for iso in "$ISO_DIR"/spaced-linux-*-amd64.iso; do
    [[ -f "$iso" ]] || continue
    name=${iso##*/}
    name=${name%.iso}
    lba=$(xorriso -indev "$iso" -find /live/filesystem.squashfs -exec report_lba -- 2>/dev/null |
        awk -F, '/^File data lba:/ {gsub(/[[:space:]]/, "", $2); print $2; exit}')
    [[ "$lba" =~ ^[0-9]+$ ]] || { echo "Cannot locate SquashFS in $iso" >&2; exit 1; }
    unsquashfs -o "$((lba * 2048))" -cat "$iso" var/lib/dpkg/status > "$OUT/$name.status"
    [[ -s "$OUT/$name.status" ]]
    printf '%s: %s package records\n' "$name" "$(grep -c '^Package:' "$OUT/$name.status")"
done
