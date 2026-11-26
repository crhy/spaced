#!/bin/bash
# Spaced 11.26.4 release-candidate build + gates (Claude 2026-11-25, based on build-rc-11263.sh). Welcome 0.1.23 and
# Monitor 0.1.10 are the pinned published artifacts (stage-external-artifacts.sh verifies their SHA-256), so nothing
# is published here. Root steps use sudo -A with an askpass helper that prints $SPACED_SUDO_PW from this process's
# environment (set by the caller for this run only; no password is ever written to disk).
# Gates run after the build: KVM BIOS + UEFI smoke, then the two-machine network-services gate (SMB/GVfs + IPP),
# which had never run before this candidate. Each gate's result is logged; the script continues past a failure so
# one run reports every gate.
set -uo pipefail
cd /home/rhy/spaced1126
V=11.26.4; LOG=build/rc-11264.log; mkdir -p build; : > "$LOG"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
[ -n "${SPACED_SUDO_PW:-}" ] || { echo 'set SPACED_SUDO_PW for this run' >&2; exit 1; }
ask=$(mktemp); cat > "$ask" <<'ASK'
#!/bin/sh
printf '%s\n' "$SPACED_SUDO_PW"
ASK
chmod 700 "$ask"
export SUDO_ASKPASS=$ask SPACED_SUDO_PW; trap 'rm -f "$ask"' EXIT
say "$V RC build start ($(git rev-parse --short HEAD) on $(git branch --show-current))"
rm -f build/iso/spaced-linux-$V-amd64.iso build/iso/spaced-linux-$V-amd64.iso.sha256
say "checks"; bash scripts/check.sh >> "$LOG" 2>&1 || { say "FAIL: check.sh"; exit 1; }
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests >> "$LOG" 2>&1 || { say "FAIL: tests"; exit 1; }
say "clean"; nice -n 10 make clean ROOT_RUN='sudo -A' >> "$LOG" 2>&1
say "lb-build (packages + ISO)"
nice -n 10 make lb-build ROOT_RUN='sudo -A' >> "$LOG" 2>&1 || { say "FAIL: lb-build"; exit 1; }
say "ISO: $(ls -la build/iso/spaced-linux-$V-amd64.iso 2>&1)"
say "sha256: $(cat build/iso/spaced-linux-$V-amd64.iso.sha256 2>&1)"
for gate in iso-smoke-kvm iso-smoke-kvm-efi network-services-gate; do
  say "gate $gate"
  if make $gate ROOT_RUN='sudo -A' >> "$LOG" 2>&1; then say "PASS: $gate"; else say "FAIL: $gate"; fi
done
say "RC build + gates done"
