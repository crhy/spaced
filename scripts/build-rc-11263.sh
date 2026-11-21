#!/bin/bash
# Spaced 11.26.3 release-candidate build (Claude 2026-11-21). Uses the LOCAL Monitor 0.1.10 and Welcome 0.1.23
# packages (verified against the pinned SHA-256 by stage-external-artifacts.sh), so nothing is published before
# rhY's go. sudo must already be authenticated by the caller; this keeps the timestamp alive (no password stored).
set -euo pipefail
cd /home/rhy/spaced1126
LOG=build/rc-11263.log; : > "$LOG"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
( while sudo -n -v 2>/dev/null; do sleep 60; done ) & keep=$!
trap 'kill $keep 2>/dev/null' EXIT
export SPACED_WELCOME_DEB=/home/rhy/spacedwelcome-11263/dist/spaced-welcome_0.1.23_all.deb
export SPACED_MONITOR_DEB=/home/rhy/spacedmonitor-0110/build/spaced-monitor_0.1.10_all.deb
say "11.26.3 RC build start ($(git rev-parse --short HEAD) on $(git branch --show-current))"
say "checks"; bash scripts/check.sh >> "$LOG" 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests >> "$LOG" 2>&1
say "clean"; nice -n 10 make clean >> "$LOG" 2>&1
say "lb-build (packages + ISO)"; nice -n 10 make lb-build ROOT_RUN=sudo >> "$LOG" 2>&1
say "ISO: $(ls -la build/iso/spaced-linux-11.26.3-amd64.iso 2>&1)"
say "sha256: $(cat build/iso/spaced-linux-11.26.3-amd64.iso.sha256 2>&1)"
say "RC build done"
