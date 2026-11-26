#!/bin/bash
# Spaced 11.26.4 installed-system gates (checklist step 5), after the published-upgrade gate: the real installer with
# encryption (#420) and with /home reuse (#413), and five elogind reboots (#409). Publishes nothing.
set -uo pipefail
cd /home/rhy/spaced1126
ISO=$PWD/build/iso/spaced-linux-11.26.4-amd64.iso; LOG=build/installed-gates-11264.log; : > "$LOG"
say() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
until grep -qE '^EXIT [0-9]+' build/published-upgrade-11264.log 2>/dev/null; do sleep 20; done
for g in "install-encrypted.sh $ISO" "install-reuse-home.sh $ISO" "reboot-loop.sh $ISO 5"; do
  say "gate $g"; if bash scripts/vm/qemu/$g >> "$LOG" 2>&1; then say "PASS: $g"; else say "FAIL($?): $g"; fi
done
say "installed gates done"
