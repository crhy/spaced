#!/bin/bash
# Spaced 11.26.3 release-candidate build (Claude 2026-11-21). Uses the LOCAL Monitor 0.1.10 and Welcome 0.1.23
# packages (verified against the pinned SHA-256 by stage-external-artifacts.sh), so nothing is published before
# rhY's go. Root steps use sudo -A with an askpass helper that prints $SPACED_SUDO_PW from this process's environment
# (set by the caller for this run only; no password is ever written to disk).
set -euo pipefail
cd /home/rhy/spaced1126
LOG=build/rc-11263.log; : > "$LOG"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
[ -n "${SPACED_SUDO_PW:-}" ] || { echo 'set SPACED_SUDO_PW for this run' >&2; exit 1; }
ask=$(mktemp); cat > "$ask" <<'ASK'
#!/bin/sh
printf '%s\n' "$SPACED_SUDO_PW"
ASK
chmod 700 "$ask"
export SUDO_ASKPASS=$ask SPACED_SUDO_PW; trap 'rm -f "$ask"' EXIT
export SPACED_WELCOME_DEB=/home/rhy/spacedwelcome-11263/dist/spaced-welcome_0.1.23_all.deb
export SPACED_MONITOR_DEB=/home/rhy/spacedmonitor-0110/build/spaced-monitor_0.1.10_all.deb
say "11.26.3 RC build start ($(git rev-parse --short HEAD) on $(git branch --show-current))"
# A previous RC ISO makes check.sh compare it with the website checksum (set only from the FINAL ISO); make clean
# removes it anyway, so remove it before the checks.
rm -f build/iso/spaced-linux-11.26.3-amd64.iso build/iso/spaced-linux-11.26.3-amd64.iso.sha256
say "checks"; bash scripts/check.sh >> "$LOG" 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests >> "$LOG" 2>&1
say "clean"; nice -n 10 make clean ROOT_RUN='sudo -A' >> "$LOG" 2>&1
say "lb-build (packages + ISO)"; nice -n 10 make lb-build ROOT_RUN='sudo -A' >> "$LOG" 2>&1
say "ISO: $(ls -la build/iso/spaced-linux-11.26.3-amd64.iso 2>&1)"
say "sha256: $(cat build/iso/spaced-linux-11.26.3-amd64.iso.sha256 2>&1)"
say "RC build done"
