#!/bin/bash
# Spaced Linux 11.26.1 release check (issues #209 and #415): really upgrade a
# running 11.26 system to 11.26.1 from the signed candidate repository.
#
# scripts/test-upgrade-packages.sh only asks APT's solver what it would do.
# This test does it for real: it boots the released 11.26 live ISO headless in
# QEMU, serves the signed candidate repository from the host over HTTP on
# 127.0.0.1 (QEMU user networking reaches the host loopback through 10.0.2.2),
# and rewrites ONLY the URL of the guest's Spaced APT source, keeping suite,
# component and signed-by exactly as shipped so APT signature checking stays
# real.  It then refreshes the lists, saves the full-upgrade simulation, and
# performs the upgrade through the old system's own Spaced Update action
# (/usr/lib/spaced-linux/spaced-update-helper all, which is what the "Update
# System" button runs through pkexec).  Finally the running system is verified:
# the reported release version, the metapackage state, dpkg/apt health, the
# elogind backport, anacron, the APT transaction guard, that the live-only
# rescue group was not pulled in, that gparted survived, that no Spaced package
# is offered again (the #209 upgrade loop) and that this boot has no segfault.
#
# Output: one PASS:/FAIL: line per check, INFO: lines for the numbers a human
# records, and a final "RESULT: PASS|FAIL passed=<n> failed=<n>".
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: upgrade-test.sh OLD_ISO REPO_DIR

Boot OLD_ISO (the released 11.26 live ISO) headless in QEMU (KVM, BIOS,
-boot order=d, no disk, VNC only, 8 GB RAM) and upgrade the running live system
to the signed candidate repository REPO_DIR:

  1. record /etc/os-release VERSION and dpkg-query -W spaced-meta elogind
  2. serve REPO_DIR with python3 -m http.server on 127.0.0.1:8930 and point
     ONLY the URL of the Spaced APT source at http://10.0.2.2:8930, keeping
     suite, component and signed-by exactly, so signature checking stays real
  3. apt-get update, then save the apt-get -s full-upgrade simulation
  4. run the old system's own Spaced Update action non-interactively as root
     (spaced-update-helper all; apt-get -y -o Dpkg::Options::=--force-confold
     full-upgrade only if that helper is not in the old image)
  5. verify the running system: the new /etc/os-release VERSION, spaced-meta
     "install ok installed <V>-1", empty dpkg --audit, apt-get check, an
     elogind +spaced<V> suffix, anacron, the APT transaction guard, no rescue
     tool newly installed, gparted still installed, no Spaced package offered
     a second time (issue #209) and no segfault in dmesg

Exit codes: 0 = PASS, 1 = FAIL, 2 = could not run.
Artifacts: build/vm-tests/v04/<iso-name>/
USAGE
}

OLD_ISO=${1:-}
REPO_DIR=${2:-}
if [ -z "$OLD_ISO" ] || [ -z "$REPO_DIR" ]; then
    usage
    exit 2
fi
if [ ! -f "$OLD_ISO" ]; then
    echo "ISO not found: $OLD_ISO" >&2
    exit 2
fi
if [ ! -d "$REPO_DIR" ]; then
    echo "Repository directory not found: $REPO_DIR" >&2
    exit 2
fi
REPO_DIR=$(cd "$REPO_DIR" && pwd)
SUITE=${SPACED_APT_SUITE:-spaced}
[[ "$SUITE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "Invalid APT suite: $SUITE" >&2; exit 2; }
if [ ! -f "$REPO_DIR/dists/$SUITE/InRelease" ]; then
    echo "The signed $SUITE repository is missing: $REPO_DIR/dists/$SUITE/InRelease (build it first)" >&2
    exit 2
fi
if [ ! -f "$REPO_DIR/dists/$SUITE/main/binary-amd64/Packages" ]; then
    echo "The signed $SUITE repository has no amd64 package index: $REPO_DIR" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
SSH_PORT=${SPACED_VM_SSH_PORT:-2232}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-45}
HTTP_PORT=${SPACED_REPO_HTTP_PORT:-8930}
RAM=${SPACED_QEMU_RAM:-8192}
CPUS=${SPACED_QEMU_CPUS:-4}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-300}
UPGRADE_TIMEOUT=${SPACED_UPGRADE_TIMEOUT:-2400}
POLL=${SPACED_VM_POLL:-5}
RELEASE_VERSION=$(cat "$PROJECT_ROOT/VERSION")
# QEMU user networking: 10.0.2.2 is the host, whose 127.0.0.1 the server binds.
REPO_URL="http://10.0.2.2:$HTTP_PORT"
# The same server, seen from the host, used only to prove it serves the metadata.
HOST_REPO_URL="http://127.0.0.1:$HTTP_PORT"
HELPER=/usr/lib/spaced-linux/spaced-update-helper
GUEST_WORK=/var/tmp/spaced-v04
# Live-USB rescue tools (issue #217 / f24): an installed system must never have
# them installed by an upgrade.
RESCUE_PACKAGES=(testdisk photorec gddrescue smartmontools lvm2 exfatprogs)
ISO_NAME=${OLD_ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_UPGRADE_TEST_DIR:-$PROJECT_ROOT/build/vm-tests/v04/$ISO_NAME}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$HTTP_PORT" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$UPGRADE_TIMEOUT"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 sshpass ssh python3; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the upgrade test" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "The upgrade test needs KVM (/dev/kvm): a 2400 s package transaction must be timed like a real PC" >&2
    exit 2
fi
SPACED_PACKAGES=$(awk '/^Package: / {print $2}' \
    "$REPO_DIR/dists/$SUITE/main/binary-amd64/Packages" | sort -u)
[ -n "$SPACED_PACKAGES" ] || { echo "No packages found in $REPO_DIR/dists/$SUITE" >&2; exit 2; }

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
# Remove evidence of a previous run of this ISO so an old log can never be
# mistaken for one of this run.
rm -f "$OUT/qemu.log" "$OUT/qemu-serial.log" "$OUT/http-server.log" \
      "$OUT/apt-update.txt" "$OUT/full-upgrade-before.txt" \
      "$OUT/full-upgrade-after.txt" "$OUT/upgrade.log" "$OUT/upgrade.status" \
      "$OUT/sources-before.txt" "$OUT/sources-after.txt" \
      "$OUT/packages-before.tsv" "$OUT/packages-after.tsv" \
      "$OUT/new-packages.txt" "$OUT/before-state.txt" "$OUT/after-state.txt"

HTTP_PID=''
QEMU_PID=''
PASSED=0
FAILED=0

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    # Both long-running helpers are our own direct children and are stopped by
    # the PIDs recorded for them, never by name matching.
    if [ -n "$HTTP_PID" ] && kill -0 "$HTTP_PID" 2>/dev/null; then
        kill "$HTTP_PID" 2>/dev/null || true
        wait "$HTTP_PID" 2>/dev/null || true
    fi
    if [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null; then
        kill "$QEMU_PID" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$QEMU_PID" 2>/dev/null || break
            sleep 0.2
        done
        kill -KILL "$QEMU_PID" 2>/dev/null || true
    fi
    [ -z "$QEMU_PID" ] || wait "$QEMU_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=15 -o ServerAliveCountMax=20 \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

# Run a python3 program in the guest (stdin) with shell-quoted arguments.
guest_python() {
    local argument quoted=''
    for argument in "$@"; do
        printf -v argument '%q' "$argument"
        quoted+=" $argument"
    done
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "python3 -$quoted"
}

ssh_is_ready() {
    local banner=
    if ! exec 3<>"/dev/tcp/127.0.0.1/$SSH_PORT" 2>/dev/null; then
        return 1
    fi
    IFS= read -r -t 2 banner <&3 || true
    exec 3<&-
    exec 3>&-
    [[ "$banner" == SSH-* ]]
}

http_is_ready() {
    [ -n "$HTTP_PID" ] && kill -0 "$HTTP_PID" 2>/dev/null || return 1
    exec 3<>"/dev/tcp/127.0.0.1/$HTTP_PORT" 2>/dev/null || return 1
    exec 3<&-
    exec 3>&-
    return 0
}

pass() {
    echo "PASS: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "FAIL: $1"
    FAILED=$((FAILED + 1))
}

check() {
    local name=$1 script=$2 out='' status=0 line shown=0
    # 'if out=$(...)' would lose the guest status: an if without else returns 0.
    out=$(guest_ssh 'bash -s' <<<"$script" 2>&1) && status=0 || status=$?
    if [ "$status" -eq 0 ]; then
        pass "$name"
        return 0
    fi
    fail "$name (guest status $status)"
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        echo "       | $line"
        shown=$((shown + 1))
        [ "$shown" -ge 8 ] && break
    done <<< "$out"
    return 0
}

show_sources() {
    local artifact=$1
    # The listing itself runs in the guest: the host's /etc/apt is irrelevant.
    # shellcheck disable=SC2016  # the $f below is the guest's, not ours
    guest_ssh 'for f in /etc/apt/sources.list /etc/apt/sources.list.d/*; do
        case "$f" in
            */sources.list|*.list|*.sources) echo "== $f"; cat "$f" ;;
        esac
    done' | tee "$OUT/$artifact"
}

echo "Starting v04 upgrade test: $OLD_ISO -> $RELEASE_VERSION from $REPO_DIR"
echo "Artifacts: $OUT"

# a. the signed candidate repository, served read-only from the host loopback
echo "Serving $REPO_DIR on http://127.0.0.1:$HTTP_PORT"
python3 -m http.server "$HTTP_PORT" --bind 127.0.0.1 --directory "$REPO_DIR" \
    > "$OUT/http-server.log" 2>&1 &
HTTP_PID=$!
echo "HTTP server PID $HTTP_PID"
started=$SECONDS
while (( SECONDS - started < 30 )); do
    http_is_ready 2>/dev/null && break
    sleep 1
done
if ! http_is_ready 2>/dev/null; then
    echo "The repository web server never listened on 127.0.0.1:$HTTP_PORT" >&2
    cat "$OUT/http-server.log" >&2
    exit 2
fi
if ! python3 - "$HOST_REPO_URL/dists/$SUITE/InRelease" "$REPO_DIR/dists/$SUITE/InRelease" <<'PY'
import sys
import urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=10) as response:
    served = response.read()
local = open(sys.argv[2], 'rb').read()
if response.status != 200 or served != local:
    raise SystemExit(f'{sys.argv[1]} did not serve the signed metadata')
PY
then
    echo "The served repository does not deliver $REPO_DIR/dists/$SUITE/InRelease" >&2
    exit 2
fi
echo "INFO: repository_url=$REPO_URL suite=$SUITE component=main signed_by=real"

# b. boot the old release headless and record what it is before the upgrade
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc -vga std -global VGA.vgamem_mb=64 \
    -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$OUT/qemu-serial.log" \
    -cdrom "$OLD_ISO" -boot order=d > "$OUT/qemu.log" 2>&1 &
QEMU_PID=$!
echo "QEMU PID $QEMU_PID (log: $OUT/qemu.log)"

started=$SECONDS
while (( SECONDS - started < BOOT_TIMEOUT )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "The VM exited early; see $OUT/qemu.log" >&2
        exit 2
    fi
    if ssh_is_ready 2>/dev/null && guest_ssh 'printf ok' >/dev/null 2>&1; then
        break
    fi
    echo "Waiting for live SSH ($((SECONDS - started))s/${BOOT_TIMEOUT}s)"
    sleep "$POLL"
done
if ! ssh_is_ready 2>/dev/null; then
    echo "The live ISO never offered SSH on port $SSH_PORT within ${BOOT_TIMEOUT}s; see $OUT/qemu.log" >&2
    exit 2
fi
echo "Live ISO is up after $((SECONDS - started))s"

guest_ssh "mkdir -p $GUEST_WORK"
{
    echo "date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    guest_ssh 'grep -E "^(NAME|VERSION|VERSION_ID|PRETTY_NAME)=" /etc/os-release'
    guest_ssh "dpkg-query -W -f='\${Package} \${db:Status-Status} \${Version}\n' spaced-meta elogind spaced-mate-default-settings spaced-themes spaced-welcome spaced-monitor anacron gparted 2>&1 || true"
    guest_ssh 'uname -r'
} | tee "$OUT/before-state.txt"
guest_ssh "dpkg-query -W -f='\${Package}\t\${db:Status-Status}\t\${Version}\n'" \
    > "$OUT/packages-before.tsv"
echo "INFO: packages_installed_before=$(awk -F'\t' '$2=="installed"' "$OUT/packages-before.tsv" | wc -l)"

# c. point ONLY the URL of the Spaced source at the local signed repository
echo "--- Spaced APT source before ---"
show_sources sources-before.txt
rewrite_status=0
guest_python "$SUITE" "$REPO_URL" > "$OUT/source-rewrite.txt" 2>&1 <<'PY' || rewrite_status=$?
# BEGIN SOURCE REWRITE (tests/test_upgrade_test_script.py runs this program)
# Rewrite ONLY the URI of the Spaced source line: suite, component and the
# [signed-by=...] option are copied through unchanged, so APT still verifies
# the candidate repository against the keyring shipped in the image.
import glob
import re
import sys

suite = sys.argv[1]
url = sys.argv[2]
apt_dir = sys.argv[3] if len(sys.argv) > 3 else '/etc/apt'
LINE = re.compile(r'^(deb)((?:[ \t]+\[[^\]]*\])?[ \t]+)(\S+)([ \t]+)(\S+)(.*)$')

changed = 0
paths = [apt_dir + '/sources.list'] + sorted(glob.glob(apt_dir + '/sources.list.d/*'))
for path in paths:
    if not path.endswith(('.list', '.sources')):
        continue
    try:
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
    except OSError:
        continue
    kept = []
    touched = False
    for line in text.splitlines(keepends=True):
        match = LINE.match(line)
        if not match or match.group(5) != suite:
            kept.append(line)
            continue
        options, current = match.group(2), match.group(3)
        if 'spaced-archive-keyring' not in options and 'spaced' not in current:
            kept.append(line)
            continue
        if current == url:
            kept.append(line)
            continue
        newline = f'{match.group(1)}{options}{url}{match.group(4)}{match.group(5)}{match.group(6)}'
        if not newline.endswith('\n'):
            newline += '\n'
        print(f'rewriting {path}')
        print(f'  before: {line.rstrip()}')
        print(f'  after:  {newline.rstrip()}')
        kept.append(newline)
        changed += 1
        touched = True
    if touched:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(''.join(kept))
print(f'changed={changed}')
sys.exit(0 if changed == 1 else 1)
# END SOURCE REWRITE
PY
cat "$OUT/source-rewrite.txt"
if [ "$rewrite_status" -ne 0 ]; then
    echo "The Spaced APT source could not be rewritten (status $rewrite_status); the upgrade would not use the candidate repository" >&2
    exit 2
fi
echo "--- Spaced APT source after ---"
show_sources sources-after.txt

# d. refresh, simulate, then really upgrade the way Spaced Update does
update_status=0
guest_ssh "apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o APT::Update::Error-Mode=any update" \
    > "$OUT/apt-update.txt" 2>&1 || update_status=$?
sed -n '1,80p' "$OUT/apt-update.txt"
if [ "$update_status" -ne 0 ]; then
    fail "d: apt-get update succeeds with the candidate repository (status $update_status)"
    grep -iE '^(W:|E:)' "$OUT/apt-update.txt" | head -n 8 | sed 's/^/       | /' || true
elif grep -qE "(Get|Hit):.*$HTTP_PORT" "$OUT/apt-update.txt" &&
     ! grep -qiE 'NO_PUBKEY|cannot be verified|The following signatures' "$OUT/apt-update.txt"; then
    pass "d: apt-get update fetches the signed $SUITE repository from $REPO_URL"
else
    fail "d: apt-get update fetches the signed $SUITE repository from $REPO_URL"
    grep -iE 'W:|E:|InRelease|Release' "$OUT/apt-update.txt" | head -n 8 | sed 's/^/       | /' || true
fi
grep -E "Get:.*$HTTP_PORT" "$OUT/apt-update.txt" | sed 's/^/INFO: spaced_source: /' || true

guest_ssh 'apt-get -s full-upgrade' > "$OUT/full-upgrade-before.txt" 2>&1 || true
grep -E '^[0-9]+ upgraded' "$OUT/full-upgrade-before.txt" | sed 's/^/INFO: simulation_before: /' || true
grep -E '^Inst ' "$OUT/full-upgrade-before.txt" | grep -Fw -e spaced-meta -e spaced-themes \
    -e spaced-mate-default-settings -e spaced-welcome -e spaced-monitor -e elogind \
    | sed 's/^/INFO: simulation_before: /' | head -n 12 || true

helper_present=0
if guest_ssh "test -x $HELPER && test ! -L $HELPER"; then
    helper_present=1
fi
if [ "$helper_present" -eq 1 ]; then
    UPGRADE_COMMAND="$HELPER all"
    echo "INFO: upgrade_command=$UPGRADE_COMMAND (the Update System action of the old release)"
else
    UPGRADE_COMMAND="apt-get -y -o Dpkg::Options::=--force-confold full-upgrade"
    echo "INFO: upgrade_command=$UPGRADE_COMMAND"
    echo "INFO: $HELPER is not runnable in the old image, so the plain non-interactive full-upgrade is used instead"
fi
# The transaction is started detached from the ssh connection: upgrading
# network-manager or dbus can drop the session, and a killed helper would leave
# the guest half-upgraded.  The status file marks the end of the transaction.
printf '%s\n' \
    '#!/bin/sh' \
    'export DEBIAN_FRONTEND=noninteractive' \
    "rm -f $GUEST_WORK/upgrade.status $GUEST_WORK/upgrade.log" \
    "timeout $UPGRADE_TIMEOUT $UPGRADE_COMMAND > $GUEST_WORK/upgrade.log 2>&1" \
    "printf '%s\n' \$? > $GUEST_WORK/upgrade.status" \
    | guest_ssh "cat > $GUEST_WORK/upgrade.sh"
guest_ssh "rm -f $GUEST_WORK/upgrade.status"
guest_ssh "chmod +x $GUEST_WORK/upgrade.sh; setsid $GUEST_WORK/upgrade.sh >/dev/null 2>&1 < /dev/null & echo started"
echo "Upgrade transaction started (timeout ${UPGRADE_TIMEOUT}s); log: $OUT/upgrade.log"
started=$SECONDS
upgrade_done=no
while (( SECONDS - started < UPGRADE_TIMEOUT + 180 )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "The VM exited during the upgrade; see $OUT/qemu.log" >&2
        exit 2
    fi
    if guest_ssh "test -f $GUEST_WORK/upgrade.status" 2>/dev/null; then
        upgrade_done=yes
        break
    fi
    echo "Upgrade running ($((SECONDS - started))s/${UPGRADE_TIMEOUT}s)"
    sleep 20
done
if [ "$upgrade_done" != yes ]; then
    echo "The upgrade transaction did not finish within ${UPGRADE_TIMEOUT}s" >&2
fi
guest_ssh "cat $GUEST_WORK/upgrade.log" > "$OUT/upgrade.log" 2>&1 || true
UPGRADE_STATUS=$(guest_ssh "cat $GUEST_WORK/upgrade.status" 2>/dev/null | tr -dc '0-9') || true
UPGRADE_STATUS=${UPGRADE_STATUS:-timeout}
echo "INFO: upgrade_status=$UPGRADE_STATUS (log: $OUT/upgrade.log)"
grep -E '^SPACED_STEP:' "$OUT/upgrade.log" | tail -n 4 | sed 's/^/INFO: /' || true
if [ "$UPGRADE_STATUS" = 0 ]; then
    pass 'd: the updater action exited 0 (the Update System action)'
else
    fail "d: the updater action exited 0 (the Update System action; exit $UPGRADE_STATUS)"
    # Everything the failing step printed, which is what the user would see.
    awk '/^SPACED_STEP:/ { step = $0; next } step != "" { print }' "$OUT/upgrade.log" |
        tail -n 12 | sed 's/^/       | /'
    grep -iE '^(E:|dpkg:|error)' "$OUT/upgrade.log" | tail -n 6 | sed 's/^/       | /' || true
    if grep -qE "grub-probe: error: failed to get canonical path of .overlay." "$OUT/upgrade.log" &&
       grep -qE '^SPACED_STEP:50:' "$OUT/upgrade.log"; then
        echo 'INFO: upgrade_failure_cause=step 65 update-grub in a LIVE session: grub-probe cannot'
        echo 'INFO:   resolve the overlay root of the live medium. Every APT/dpkg step of the'
        echo 'INFO:   transaction had already completed; see the e: checks below for the result.'
    fi
fi

# e. verify the running upgraded system
{
    echo "date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    guest_ssh 'grep -E "^(NAME|VERSION|VERSION_ID|PRETTY_NAME)=" /etc/os-release'
    guest_ssh "dpkg-query -W -f='\${Package} \${db:Status-Status} \${Version}\n' spaced-meta elogind spaced-mate-default-settings spaced-themes spaced-welcome spaced-monitor anacron gparted 2>&1 || true"
    guest_ssh 'uname -r'
} | tee "$OUT/after-state.txt"
guest_ssh "dpkg-query -W -f='\${Package}\t\${db:Status-Status}\t\${Version}\n'" \
    > "$OUT/packages-after.tsv"
echo "INFO: packages_installed_after=$(awk -F'\t' '$2=="installed"' "$OUT/packages-after.tsv" | wc -l)"

check "e: /etc/os-release VERSION is \"$RELEASE_VERSION\"" "
if grep -qxF 'VERSION=\"$RELEASE_VERSION\"' /etc/os-release; then exit 0; fi
grep -E '^(VERSION|VERSION_ID)=' /etc/os-release >&2
exit 1
"
check "e: spaced-meta is install ok installed $RELEASE_VERSION-1" "
status=\$(dpkg-query -W -f='\${Status} \${Version}' spaced-meta 2>&1)
if [ \"\$status\" = 'install ok installed $RELEASE_VERSION-1' ]; then exit 0; fi
echo \"spaced-meta: \$status\" >&2
exit 1
"
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'e: dpkg --audit prints nothing' '
out=$(dpkg --audit)
test -z "$out" || { echo "$out" >&2; exit 1; }
'
check 'e: apt-get check exits 0' 'apt-get check'
check "e: elogind version ends with +spaced$RELEASE_VERSION" "
got=\$(dpkg-query -W -f='\${Version}' elogind)
case \"\$got\" in
    *+spaced$RELEASE_VERSION) exit 0 ;;
esac
echo \"elogind version is '\$got', expected a +spaced$RELEASE_VERSION suffix\" >&2
exit 1
"
check 'e: anacron is installed' "
status=\$(dpkg-query -W -f='\${db:Status-Status}' anacron 2>&1)
test \"\$status\" = installed || { echo \"anacron: \$status\" >&2; exit 1; }
"
check 'e: /etc/apt/apt.conf.d/60spaced-transaction-guard exists' \
      'test -f /etc/apt/apt.conf.d/60spaced-transaction-guard'

# The live-only rescue group must never be pulled in by an upgrade (f24).
installed_names() {
    awk -F'\t' '$2=="installed" {print $1}' "$1" | sort -u
}
comm -13 <(installed_names "$OUT/packages-before.tsv") <(installed_names "$OUT/packages-after.tsv") \
    > "$OUT/new-packages.txt"
while IFS= read -r package; do
    version=$(awk -F'\t' -v p="$package" '$1==p {print $3; exit}' "$OUT/packages-after.tsv")
    echo "INFO: newly_installed: $package $version"
done < "$OUT/new-packages.txt"
new_rescue=''
for package in "${RESCUE_PACKAGES[@]}"; do
    if grep -qx "$package" "$OUT/new-packages.txt"; then
        new_rescue+="$package "
    fi
done
if [ -z "$new_rescue" ]; then
    pass "e: none of ${RESCUE_PACKAGES[*]} was newly installed by the upgrade"
else
    fail "e: none of ${RESCUE_PACKAGES[*]} was newly installed by the upgrade (new: $new_rescue)"
fi
check 'e: gparted is still installed' "
status=\$(dpkg-query -W -f='\${db:Status-Status}' gparted 2>&1)
test \"\$status\" = installed || { echo \"gparted: \$status\" >&2; exit 1; }
"

# Issue #209: a second simulation must offer no Spaced package again.
guest_ssh 'apt-get -s full-upgrade' > "$OUT/full-upgrade-after.txt" 2>&1 || true
grep -E '^[0-9]+ upgraded' "$OUT/full-upgrade-after.txt" | sed 's/^/INFO: simulation_after: /' || true
loop_packages=$(grep -E '^Inst ' "$OUT/full-upgrade-after.txt" |
    awk '{ sub(/:.*/, "", $2); print $2 }' | grep -Fx -f <(printf '%s\n' "$SPACED_PACKAGES") || true)
if [ -z "$loop_packages" ]; then
    pass 'e: no Spaced package is offered again (no upgrade loop, issue #209)'
else
    fail 'e: no Spaced package is offered again (no upgrade loop, issue #209)'
    printf '       | still offered: %s\n' "$loop_packages"
    grep -E '^[0-9]+ upgraded' "$OUT/full-upgrade-after.txt" | sed 's/^/       | /' || true
fi
# shellcheck disable=SC2016  # the $... below runs in the guest, not here
check 'e: dmesg has no segfault line' '
count=$(dmesg | grep -ci segfault || true)
test "${count:-0}" -eq 0 || { dmesg | grep -i segfault >&2; exit 1; }
'

echo "Artifacts: $OUT"
if [ "$FAILED" -eq 0 ]; then
    echo "RESULT: PASS passed=$PASSED failed=$FAILED"
    exit 0
fi
echo "RESULT: FAIL passed=$PASSED failed=$FAILED"
exit 1
