#!/bin/bash
# Spaced Linux 11.26.1 release measurement: boot one live ISO headless in KVM
# exactly the way scripts/vm/qemu/live-checks.sh boots it, and record the
# efficiency numbers a human compares between two releases. One cold boot per
# run; run it three times per ISO and compare the medians.
#
# Measured per boot (nothing in the guest is changed, everything is read):
#   * seconds from the QEMU start to mate-panel + caja + compiz running
#   * guest /proc/uptime at that moment (boot time without systemd-analyze)
#   * used memory and process count after IDLE_SECONDS of idle
#   * total RSS of the 10 biggest processes
#   * context switches/s and interrupts/s while idle (/proc/stat, /proc/interrupts)
#   * idle CPU % over the same window (/proc/stat cpu line delta)
#   * disk reads during boot (/proc/diskstats, cumulative at desktop-ready)
#   * duration of apt-get check and dpkg --audit (two runs each)
#   * how often the spaced-display-repair --watch helper wakes up over
#     WATCH_SECONDS idle: nr_switches of every task in its process tree
#     (/proc/<pid>/sched), the CPU jiffies those wake-ups cost, and how many
#     times its reconcile `sleep` child was replaced. 11.26 reconciled DPMS
#     every 30 s, 11.26.1 every 300 s.
#
# Output: INFO: name=value lines (raw snapshots are kept in the artifact dir),
# PASS:/FAIL: lines for the sanity checks, and a final RESULT: line.
#
# Exit codes: 0 = PASS (all metrics collected), 1 = FAIL (a metric or a sanity
# check failed), 2 = could not run (bad arguments, no KVM, no SSH, no desktop).
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: release-measure.sh ISO [RUN-LABEL]

Boot the live ISO cold in QEMU (KVM, BIOS, -boot order=d, no disk, VNC only,
4096 MiB, 4 CPUs) and print the release-comparison measurements as INFO: lines.
RUN-LABEL only names the artifact directory (default 1).

Environment: SPACED_VM_SSH_PORT (2234), SPACED_QEMU_VNC_DISPLAY (45),
SPACED_QEMU_RAM (4096), SPACED_QEMU_CPUS (4), SPACED_ISO_BOOT_TIMEOUT (300),
SPACED_DESKTOP_TIMEOUT (180), SPACED_MEASURE_IDLE_SECONDS (60),
SPACED_MEASURE_WATCH_SECONDS (120), SPACED_MEASURE_DIR.

Artifacts: build/vm-tests/r02/<iso-name>/run-<RUN-LABEL>/
USAGE
}

ISO=${1:-}
RUN_LABEL=${2:-1}
if [ -z "$ISO" ]; then
    usage
    exit 2
fi
if [ ! -f "$ISO" ]; then
    echo "ISO not found: $ISO" >&2
    exit 2
fi
if ! [[ "$RUN_LABEL" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Invalid run label: $RUN_LABEL" >&2
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
SSH_PORT=${SPACED_VM_SSH_PORT:-2234}
VNC_DISPLAY=${SPACED_QEMU_VNC_DISPLAY:-45}
RAM=${SPACED_QEMU_RAM:-4096}
CPUS=${SPACED_QEMU_CPUS:-4}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
BOOT_TIMEOUT=${SPACED_ISO_BOOT_TIMEOUT:-300}
DESKTOP_TIMEOUT=${SPACED_DESKTOP_TIMEOUT:-180}
IDLE_SECONDS=${SPACED_MEASURE_IDLE_SECONDS:-60}
WATCH_SECONDS=${SPACED_MEASURE_WATCH_SECONDS:-120}
SSH_POLL=${SPACED_SSH_POLL_SECONDS:-2}
DESKTOP_POLL=${SPACED_DESKTOP_POLL_SECONDS:-1}
ISO_NAME=${ISO##*/}
ISO_NAME=${ISO_NAME%.iso}
OUT=${SPACED_MEASURE_DIR:-$PROJECT_ROOT/build/vm-tests/r02/$ISO_NAME/run-$RUN_LABEL}

for value in "$SSH_PORT" "$VNC_DISPLAY" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$DESKTOP_TIMEOUT" \
             "$IDLE_SECONDS" "$WATCH_SECONDS" "$SSH_POLL" "$DESKTOP_POLL"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
for tool in qemu-system-x86_64 sshpass ssh python3 awk; do
    command -v "$tool" >/dev/null || { echo "$tool is required for the release measurements" >&2; exit 2; }
done
if [ ! -e /dev/kvm ]; then
    echo "The release measurements need KVM (/dev/kvm): boot time must be timed on real hardware" >&2
    exit 2
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
# Remove evidence of a previous run in this directory so an old snapshot can
# never be mistaken for one of this run.
rm -f "$OUT"/*.txt "$OUT"/*.log "$OUT"/guest-*.sh "$OUT"/ssh-ctl*

QEMU_PID=''
SSH_CTRL=''
PASSED=0
FAILED=0

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    if [ -n "$SSH_CTRL" ]; then
        SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ControlPath="$SSH_CTRL" \
            -O exit root@127.0.0.1 >/dev/null 2>&1 || true
    fi
    # QEMU is our own direct child; it is stopped by that recorded PID only.
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

# The live image regenerates its SSH host keys on every boot, so a fresh live
# boot must not pin them (same as scripts/vm/qemu/live-checks.sh).
guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -o ControlPath="${SSH_CTRL:-none}" \
        root@127.0.0.1 "$@"
}

# One shared connection: the desktop-ready poll runs every second, and a fresh
# SSH handshake each time would both slow the poll and load the idle guest.
open_ssh_master() {
    local candidate="$OUT/ssh-ctl"
    if SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ControlMaster=yes \
        -o ControlPath="$candidate" -o ConnectTimeout=10 -o ServerAliveInterval=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -fN root@127.0.0.1 2>>"$OUT/ssh.log"; then
        if SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$SSH_PORT" -o ControlPath="$candidate" \
            -O check root@127.0.0.1 2>/dev/null; then
            SSH_CTRL=$candidate
            return 0
        fi
    fi
    echo "WARNING: no shared SSH connection; polling is slower but still valid" >&2
    return 0
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

info() { echo "INFO: $1=$2"; }

fail() {
    FAILED=$((FAILED + 1))
    echo "FAIL: $1"
}

pass() {
    PASSED=$((PASSED + 1))
    echo "PASS: $1"
}

elapsed_seconds() {
    awk -v start="$1" -v end="$2" 'BEGIN { printf "%.1f", (end - start) / 1000000000 }'
}

ISO_SIZE=$(stat -c %s "$ISO")
ISO_SHA=$(awk 'NR==1 { print $1 }' "$ISO.sha256" 2>/dev/null || true)

info iso_name "$ISO_NAME"
info run_label "$RUN_LABEL"
info iso_path "$ISO"
info iso_size_bytes "$ISO_SIZE"
info iso_size_mib "$(awk -v b="$ISO_SIZE" 'BEGIN { printf "%.1f", b / 1048576 }')"
info iso_sha256_expected "${ISO_SHA:-none}"
info vm_flags "-enable-kvm -cpu host -m $RAM -smp $CPUS -vga std -display none -cdrom ISO -boot order=d"
info host_cpus "$(nproc)"
info host_load_at_start "$(cut -d' ' -f1-3 /proc/loadavg)"
info idle_seconds "$IDLE_SECONDS"
info watch_seconds "$WATCH_SECONDS"

echo "Starting release-measure on $ISO ($RAM MiB, $CPUS CPUs, KVM/BIOS, SSH 127.0.0.1:$SSH_PORT)"
echo "Artifacts: $OUT"

QEMU_START_NS=$(date +%s%N)
qemu-system-x86_64 -enable-kvm -cpu host -m "$RAM" -smp "$CPUS" \
    -device qemu-xhci,id=xhci \
    -device usb-kbd,bus=xhci.0 -device usb-tablet,bus=xhci.0 \
    -nic "user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -rtc base=utc -vga std -global VGA.vgamem_mb=64 \
    -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -serial "file:$OUT/qemu-serial.log" \
    -cdrom "$ISO" -boot order=d > "$OUT/qemu.log" 2>&1 &
QEMU_PID=$!
info qemu_pid "$QEMU_PID"
echo "QEMU PID $QEMU_PID (log: $OUT/qemu.log)"

started=$SECONDS
SSH_READY=no
while (( SECONDS - started < BOOT_TIMEOUT )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "The VM exited early; see $OUT/qemu.log" >&2
        exit 2
    fi
    if ssh_is_ready 2>/dev/null && guest_ssh 'printf ok' >/dev/null 2>&1; then
        SSH_READY=yes
        SSH_READY_NS=$(date +%s%N)
        break
    fi
    echo "Waiting for live SSH ($((SECONDS - started))s/${BOOT_TIMEOUT}s)"
    sleep "$SSH_POLL"
done
if [ "$SSH_READY" != yes ]; then
    echo "The live ISO never offered SSH on port $SSH_PORT within ${BOOT_TIMEOUT}s; see $OUT/qemu.log" >&2
    exit 2
fi
info ssh_ready_seconds "$(elapsed_seconds "$QEMU_START_NS" "$SSH_READY_NS")"
open_ssh_master

# Desktop ready = mate-panel, caja and compiz all running. The guest uptime is
# read in the same command so it costs no extra round trip.
DESKTOP_READY=no
UPTIME_AT_READY=unknown
started=$SECONDS
while (( SECONDS - started < DESKTOP_TIMEOUT )); do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        echo "The VM exited while waiting for the desktop; see $OUT/qemu.log" >&2
        exit 2
    fi
    if ready_out=$(guest_ssh 'if pgrep -x mate-panel >/dev/null && pgrep -x caja >/dev/null && pgrep -x compiz >/dev/null; then cut -d" " -f1 /proc/uptime; else exit 1; fi' 2>/dev/null); then
        DESKTOP_READY_NS=$(date +%s%N)
        UPTIME_AT_READY=$(printf '%s' "$ready_out" | tr -dc '0-9.')
        DESKTOP_READY=yes
        break
    fi
    echo "Waiting for the live desktop ($((SECONDS - started))s/${DESKTOP_TIMEOUT}s)"
    sleep "$DESKTOP_POLL"
done
if [ "$DESKTOP_READY" != yes ]; then
    echo "The live desktop (mate-panel, caja, compiz) never started within ${DESKTOP_TIMEOUT}s" >&2
    fail 'desktop ready within timeout'
else
    pass 'desktop ready within timeout'
fi
info desktop_ready_seconds "$(elapsed_seconds "$QEMU_START_NS" "${DESKTOP_READY_NS:-$SSH_READY_NS}")"
info uptime_at_desktop_ready_s "$UPTIME_AT_READY"
info host_load_at_desktop "$(cut -d' ' -f1-3 /proc/loadavg)"

if [ "$DESKTOP_READY" = yes ]; then
    for process in mate-panel caja compiz; do
        if guest_ssh "pgrep -x $process >/dev/null" 2>/dev/null; then
            pass "desktop: $process runs"
        else
            fail "desktop: $process runs"
        fi
    done
    info os_version "$(guest_ssh 'sed -n s/^VERSION=//p /etc/os-release' 2>/dev/null | tr -d '"')"
    info guest_kernel "$(guest_ssh 'uname -r' 2>/dev/null | tr -d '\n')"
    # Cumulative since boot: the disk reads the boot itself caused.
    guest_ssh 'cat /proc/diskstats' > "$OUT/diskstats-at-ready.txt" 2>/dev/null || true
fi

# The idle window runs inside one SSH session: both /proc snapshots are taken in
# the guest with the guest clock, so SSH round trips never widen the window.
cat > "$OUT/guest-idle-window.sh" <<'GUEST'
echo "===MARK stat0==="
grep -E '^(cpu |ctxt |intr )' /proc/stat
echo "===MARK interrupts0==="
cat /proc/interrupts
echo "===MARK io0==="
for io in /proc/[0-9]*/io; do
    pid=${io#/proc/}
    pid=${pid%/io}
    comm=$(cat "/proc/$pid/comm" 2>/dev/null)
    rchar=$(awk '/^rchar:/ { print $2 }' "$io" 2>/dev/null)
    read_bytes=$(awk '/^read_bytes:/ { print $2 }' "$io" 2>/dev/null)
    echo "$pid ${comm:-?} ${rchar:-0} ${read_bytes:-0}"
done
echo "===MARK t0==="
date +%s%N
sleep "$IDLE_SECONDS"
echo "===MARK t1==="
date +%s%N
echo "===MARK stat1==="
grep -E '^(cpu |ctxt |intr )' /proc/stat
echo "===MARK interrupts1==="
cat /proc/interrupts
echo "===MARK io1==="
for io in /proc/[0-9]*/io; do
    pid=${io#/proc/}
    pid=${pid%/io}
    comm=$(cat "/proc/$pid/comm" 2>/dev/null)
    rchar=$(awk '/^rchar:/ { print $2 }' "$io" 2>/dev/null)
    read_bytes=$(awk '/^read_bytes:/ { print $2 }' "$io" 2>/dev/null)
    echo "$pid ${comm:-?} ${rchar:-0} ${read_bytes:-0}"
done
echo "===MARK end==="
GUEST
guest_ssh "IDLE_SECONDS=$IDLE_SECONDS bash -s" < "$OUT/guest-idle-window.sh" \
    > "$OUT/idle-window.txt" 2>&1 || true
if [ -s "$OUT/idle-window.txt" ]; then
    python3 - "$OUT/idle-window.txt" <<'PY'
import re
import sys

blocks = {}
current = None
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    match = re.match(r'===MARK (\w+)===\s*$', line)
    if match:
        current = match.group(1)
        blocks[current] = []
    elif current is not None:
        blocks[current].append(line.rstrip('\n'))


def field(lines, prefix):
    for line in lines:
        if line.startswith(prefix):
            return line.split()[1:]
    raise SystemExit('missing %s in %s' % (prefix, sys.argv[1]))


def emit(name, value):
    print('INFO: %s=%s' % (name, value))


cpu0 = [int(x) for x in field(blocks['stat0'], 'cpu ')]
cpu1 = [int(x) for x in field(blocks['stat1'], 'cpu ')]
ctxt0 = int(field(blocks['stat0'], 'ctxt ')[0])
ctxt1 = int(field(blocks['stat1'], 'ctxt ')[0])
intr0 = int(field(blocks['stat0'], 'intr ')[0])
intr1 = int(field(blocks['stat1'], 'intr ')[0])
t0 = int(blocks['t0'][0])
t1 = int(blocks['t1'][0])
elapsed = (t1 - t0) / 1e9

emit('idle_window_seconds', '%.1f' % elapsed)
emit('context_switches_per_s', '%.1f' % ((ctxt1 - ctxt0) / elapsed))
emit('interrupts_per_s', '%.1f' % ((intr1 - intr0) / elapsed))
total_delta = sum(cpu1) - sum(cpu0)
idle_delta = (cpu1[3] + cpu1[4]) - (cpu0[3] + cpu0[4])
emit('idle_cpu_percent', '%.2f' % (100.0 * (total_delta - idle_delta) / max(total_delta, 1)))


def irq_totals(lines):
    totals = {}
    for line in lines:
        parts = line.split()
        if len(parts) < 3 or not parts[0].endswith(':'):
            continue
        counts = [int(x) for x in parts[1:] if x.isdigit()]
        if counts:
            totals[' '.join(parts[-2:])] = sum(counts)
    return totals


before = irq_totals(blocks['interrupts0'])
after = irq_totals(blocks['interrupts1'])
for delta, label in sorted(((after.get(k, 0) - before.get(k, 0), k)
                            for k in set(before) | set(after)), reverse=True)[:6]:
    if delta:
        emit('irq_delta_per_s', '%.1f %s' % (delta / elapsed, label.replace(' ', '_')))


def io_totals(lines):
    totals = {}
    for line in lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        pid, comm, rchar, read_bytes = parts
        key = comm + '#' + pid
        totals[key] = (int(rchar), int(read_bytes))
    return totals


io_before = io_totals(blocks.get('io0', []))
io_after = io_totals(blocks.get('io1', []))
for name, index in (('rchar', 0), ('read_bytes', 1)):
    deltas = sorted(
        ((io_after.get(k, (0, 0))[index] - io_before.get(k, (0, 0))[index], k)
         for k in set(io_before) | set(io_after)), reverse=True)
    for delta, key in deltas[:5]:
        if delta > 0:
            emit('io_%s_per_s' % name, '%d %s' % (delta / elapsed, key))
PY
else
    fail 'idle window snapshot captured'
fi

# Memory, process count, biggest processes and package count, after the idle
# window. dpkg-query only reads, it never installs or removes anything.
if [ "$DESKTOP_READY" = yes ]; then
    info mem_used_mib "$(guest_ssh 'free -m' 2>/dev/null | awk '/^Mem:/{print $3}')"
    info mem_total_mib "$(guest_ssh 'free -m' 2>/dev/null | awk '/^Mem:/{print $2}')"
    info mem_available_mib "$(guest_ssh 'free -m' 2>/dev/null | awk '/^Mem:/{print $7}')"
    info process_count "$(guest_ssh 'ps -e --no-headers | wc -l' 2>/dev/null | tr -d '[:space:]')"
    # shellcheck disable=SC2016  # the awk program below runs in the guest, not here
    info top10_rss_kib "$(guest_ssh 'ps -eo rss= --sort=-rss | head -n 10 | awk "{s += \$1} END {print s+0}"' 2>/dev/null | tr -d '[:space:]')"
    # shellcheck disable=SC2016  # the awk program below runs in the guest, not here
    info top10_rss_mib "$(guest_ssh 'ps -eo rss= --sort=-rss | head -n 10 | awk "{s += \$1} END {printf \"%.1f\", s/1024}"' 2>/dev/null | tr -d '[:space:]')"
    guest_ssh 'ps -eo rss=,pid=,comm= --sort=-rss | head -n 10' 2>/dev/null |
        awk '{ rss = $1; pid = $2; $1 = ""; $2 = ""; sub(/^[ \t]+/, "");
               printf "INFO: biggest_rss: rss_kB=%s pid=%s comm=%s\n", rss, pid, $0 }' |
        tee "$OUT/top10-rss.txt" >/dev/null
    # shellcheck disable=SC2016  # ${Package} is expanded by dpkg-query in the guest
    info package_count "$(guest_ssh 'dpkg-query -W -f="${Package}\n" 2>/dev/null | wc -l' 2>/dev/null | tr -d '[:space:]')"
    guest_ssh 'cat /proc/diskstats' > "$OUT/diskstats-after-idle.txt" 2>/dev/null || true
    for file in diskstats-at-ready diskstats-after-idle; do
        [ -s "$OUT/$file.txt" ] || continue
        awk -v label="$file" '
            $4 + 0 > 0 { printf "INFO: %s: device=%s reads_completed=%d sectors_read=%d mib_read=%.1f\n",
                         label, $3, $4, $6, $6 * 512 / 1048576 }' "$OUT/$file.txt"
    done
fi

# apt-get check and dpkg --audit, timed twice each inside the guest.
cat > "$OUT/guest-apt-dpkg.sh" <<'GUEST'
for run in 1 2; do
    t0=$(date +%s%N)
    apt-get check >/dev/null 2>&1
    rc=$?
    t1=$(date +%s%N)
    echo "INFO: apt_get_check: run=$run rc=$rc ms=$(( (t1 - t0) / 1000000 ))"
done
for run in 1 2; do
    t0=$(date +%s%N)
    out=$(dpkg --audit 2>&1)
    rc=$?
    t1=$(date +%s%N)
    echo "INFO: dpkg_audit: run=$run rc=$rc ms=$(( (t1 - t0) / 1000000 )) output_bytes=${#out}"
done
GUEST
guest_ssh 'bash -s' < "$OUT/guest-apt-dpkg.sh" > "$OUT/apt-dpkg-timing.txt" 2>&1 || true
grep -E '^INFO: (apt_get_check|dpkg_audit):' "$OUT/apt-dpkg-timing.txt" || true
if grep -q 'apt_get_check: run=1 rc=0' "$OUT/apt-dpkg-timing.txt"; then
    pass 'apt-get check exits 0'
else
    fail 'apt-get check exits 0'
fi
if grep -q 'dpkg_audit: run=1 rc=0 ms=[0-9][0-9]* output_bytes=0' "$OUT/apt-dpkg-timing.txt"; then
    pass 'dpkg --audit is clean'
else
    fail 'dpkg --audit is clean'
fi

# The login-path helper 11.26.1 changed: how often spaced-display-repair --watch
# wakes up while the desktop is idle. nr_switches counts every schedule of every
# task in the helper's process tree (one wake-up plus one block per round), the
# CPU jiffies count what those rounds cost including the reaped gsettings/xset
# children, and a replaced `sleep` child is exactly one reconcile round.
cat > "$OUT/guest-display-repair.sh" <<'GUEST'
tree_pids=''
sched_seen=0
collect() {
    local roots frontier p c
    roots=$(pgrep -f 'spaced-display[-]repair' | tr '\n' ' ')
    tree_pids=$roots
    frontier=$roots
    while [ -n "$frontier" ]; do
        next=''
        for p in $frontier; do
            for c in $(ps -o pid= --ppid "$p" 2>/dev/null); do
                case " $tree_pids " in
                    *" $c "*) continue ;;
                esac
                tree_pids="$tree_pids $c"
                next="$next $c"
            done
        done
        frontier=$next
    done
}
sample() {
    local p line rest switches cpu
    switches=0
    cpu=0
    sched_seen=0
    for p in $tree_pids; do
        [ -r "/proc/$p/stat" ] || continue
        line=$(cat "/proc/$p/stat")
        rest=${line##*) }
        set -- $rest
        # fields after comm: state ... utime=${12} stime=${13} cutime=${14}
        # cstime=${15}. ${NN} is required: bash reads a bare $12 as $1 "2".
        cpu=$(( cpu + ${12} + ${13} + ${14} + ${15} ))
        if [ -r "/proc/$p/sched" ]; then
            sched_seen=$(( sched_seen + 1 ))
            switches=$(( switches + $(awk -F: '/nr_switches/ { gsub(/ /, "", $2); print $2 }' \
                "/proc/$p/sched") ))
        fi
    done
    echo "switches=$switches cpu_jiffies=$cpu sched_tasks=$sched_seen"
    ps -eo pid=,ppid=,etimes=,comm= | awk -v pids=" $tree_pids " '
        index(pids, " " $2 " ") && $4 == "sleep" {
            print "sleep_child pid=" $1 " ppid=" $2 " etimes=" $3 }'
}
collect
echo "===MARK pids==="
echo "pids $tree_pids"
echo "===MARK sample0==="
sample
echo "===MARK t0==="
date +%s%N
sleep "$WATCH_SECONDS"
echo "===MARK t1==="
date +%s%N
echo "===MARK sample1==="
sample
echo "===MARK end==="
GUEST
if [ "$DESKTOP_READY" = yes ]; then
    guest_ssh "WATCH_SECONDS=$WATCH_SECONDS bash -s" < "$OUT/guest-display-repair.sh" \
        > "$OUT/display-repair-window.txt" 2>&1 || true
    if grep -q '^switches=' "$OUT/display-repair-window.txt"; then
        python3 - "$OUT/display-repair-window.txt" "$WATCH_SECONDS" <<'PY'
import re
import sys

blocks = {}
current = None
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    match = re.match(r'===MARK (\w+)===\s*$', line)
    if match:
        current = match.group(1)
        blocks[current] = []
    elif current is not None:
        blocks[current].append(line.rstrip('\n'))

watch = float(sys.argv[2])
pids = [token for token in ' '.join(blocks.get('pids', [])).split() if token.isdigit()]
print('INFO: display_repair_pids=%s' % (' '.join(pids) or 'none'))
first = next((line for line in blocks.get('sample0', []) if line.startswith('switches=')), None)
last = next((line for line in blocks.get('sample1', []) if line.startswith('switches=')), None)
if not first or not last:
    raise SystemExit('no spaced-display-repair sample in %s' % sys.argv[1])
before = dict(kv.split('=') for kv in first.split())
after = dict(kv.split('=') for kv in last.split())
t0 = int(blocks['t0'][0])
t1 = int(blocks['t1'][0])
elapsed = (t1 - t0) / 1e9
print('INFO: display_repair_window_seconds=%.1f' % elapsed)
print('INFO: display_repair_sched_tasks=%s' % after['sched_tasks'])
print('INFO: display_repair_nr_switches_delta=%d' % (int(after['switches']) - int(before['switches'])))
print('INFO: display_repair_nr_switches_per_s=%.3f'
      % ((int(after['switches']) - int(before['switches'])) / elapsed))
print('INFO: display_repair_cpu_jiffies_delta=%d'
      % (int(after['cpu_jiffies']) - int(before['cpu_jiffies'])))
seen = []
for block in ('sample0', 'sample1'):
    for line in blocks.get(block, []):
        match = re.match(r'sleep_child pid=(\d+) ppid=(\d+) etimes=(\d+)', line)
        if match and match.group(1) not in seen:
            seen.append(match.group(1))
            print('INFO: display_repair_sleep_child: %s' % line)
print('INFO: display_repair_sleep_children_seen=%d' % len(seen))
PY
        if grep -Eq '^pids [0-9]' "$OUT/display-repair-window.txt"; then
            pass 'spaced-display-repair --watch runs in the live session'
        else
            fail 'spaced-display-repair --watch runs in the live session'
        fi
    else
        fail 'spaced-display-repair wake-up window captured'
    fi
fi

echo "Artifacts: $OUT"
info host_load_at_end "$(cut -d' ' -f1-3 /proc/loadavg)"
if [ "$FAILED" -eq 0 ] && [ "$DESKTOP_READY" = yes ]; then
    echo "RESULT: PASS passed=$PASSED failed=$FAILED"
    exit 0
fi
echo "RESULT: FAIL passed=$PASSED failed=$FAILED"
exit 1
