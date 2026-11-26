#!/bin/bash
# Spaced 11.26.4 release gates after the RC build (Claude 2026-11-26, rhY: "make sure windows networking works and
# networked printers are discoverable"). Runs only if build-rc-11264.sh built the ISO and its KVM + network-services
# gates passed. Then: VirtualBox smokes (checklist step 4), the APT candidate (step 8 build) and the published-upgrade
# network gate from the public 11.26.3 ISO (two upgraded clients must do SMB/GVfs + IPP). Publishes NOTHING.
# Root steps use sudo -A with an askpass helper fed from $SPACED_SUDO_PW (never written to disk).
set -uo pipefail
cd /home/rhy/spaced1126
LOG=build/release-gates-11264.log; : > "$LOG"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
[ -n "${SPACED_SUDO_PW:-}" ] || { echo 'set SPACED_SUDO_PW' >&2; exit 1; }
ask=$(mktemp); printf '#!/bin/sh\nprintf "%%s\\n" "$SPACED_SUDO_PW"\n' > "$ask"; chmod 700 "$ask"
export SUDO_ASKPASS=$ask SPACED_SUDO_PW; trap 'rm -f "$ask"' EXIT
rc=build/rc-11264.log
for need in 'PASS: iso-smoke-kvm$' 'PASS: iso-smoke-kvm-efi$' 'PASS: network-services-gate$'; do
  grep -qE "$need" "$rc" || { say "STOP: RC log lacks '$need' - fix first"; exit 1; }
done
fails=0
gate() { say "gate $*"; if "$@" >> "$LOG" 2>&1; then say "PASS: $*"; else say "FAIL($?): $*"; fails=$((fails+1)); fi; }
gate make vbox-smoke ROOT_RUN='sudo -A'
say "vbox-smoke-default (exit 3 = Compiz cannot start on VirtualBox's own controller, #218: recorded, not hidden)"
make vbox-smoke-default ROOT_RUN='sudo -A' >> "$LOG" 2>&1; r=$?; say "vbox-smoke-default exit $r"
gate make apt-repo ROOT_RUN='sudo -A'
gate make published-upgrade-network-gate ROOT_RUN='sudo -A' UPGRADE_BASE_VERSION=11.26.3 \
     UPGRADE_STATUS_FILES="$(ls build/upgrade-status/*.status | tr '\n' ' ')"
say "release gates done: $fails failed"
