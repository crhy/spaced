#!/bin/bash
# Issue #424 / task b02: why does the Spaced guest burn ~28 % CPU and ~15,900
# context switches/s while it sits idle in the bench VM? run-bench.sh measured
# it; this script localises it. It boots ONE ISO from scripts/vm/bench/matrix.
# conf in a fresh KVM VM with the runner's machine spec (same -cpu host, 4
# vCPU, 8 GiB, 40G qcow2 under BENCH_VM_DIR/<os>/, headless, VNC on 127.0.0.1
# only), gets a shell the way the runner does (SSH for access=ssh, typed
# commands over QMP for access=qmp), and inside the guest waits until the
# uptime reaches --wait-until seconds before sampling a --window second
# window: per-process CPU ticks and context-switch deltas from /proc, the
# /proc/stat totals over the SAME window, and /proc/interrupts deltas.
#
# Suspects are injected with one guest command before the sample:
#   --suspect '<one guest command>'   run as root over SSH (spaced) before the
#                                     sampler starts
#   --no-ssh-idle                     spaced: start the sampler detached with
#                                     nohup and disconnect, so no SSH session
#                                     is open while the sample runs
#
# Results land on the host as
#   build/bench/idle-<os>-<label>.tsv          pid comm cpu_pct ctxt_per_s args
#   build/bench/idle-<os>-<label>-totals.txt  uptime_at_sample, cpu_in_use_pct,
#                                             ctxt_per_s, intr_per_s,
#                                             sum_of_process_cpu_pct, top
#                                             interrupts, and what was run
# The VM and its whole disk are destroyed when the run is done or on error.
#
# Usage: idle-investigate.sh <os-label> <run-label> [OPTION]...
#   --suspect '<one guest command>'  one guest command run before the sample
#   --no-ssh-idle                    ssh guests: sampler detached, session closed
#   --wait-until SECONDS             sample only after this uptime (default 180)
#   --window SECONDS                 sample length (default 60)
#
# Environment: BENCH_VM_DIR (/media/rhy/data/bench-vms), BENCH_QEMU_RAM (8192),
# BENCH_QEMU_CPUS (4), BENCH_DISK_SIZE (40G), BENCH_HTTP_PORT (8099),
# BENCH_VM_SSH_PORT (2240), BENCH_VNC_DISPLAY (121), BENCH_ISO_BOOT_TIMEOUT
# (300), BENCH_BOOT_MENU_TAPS (3), BENCH_OUT_DIR (build/bench),
# SPACED_LIVE_ROOT_PASSWORD (spaced).
set -euo pipefail

usage() {
    sed -n '/^# Usage:/,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//;$d' >&2
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
# shellcheck source=../qemu/common.sh
source "$SCRIPT_DIR/../qemu/common.sh"

MATRIX=${IDLE_MATRIX:-$SCRIPT_DIR/matrix.conf}
OUT_DIR=${BENCH_OUT_DIR:-$PROJECT_ROOT/build/bench}
VM_DIR_ROOT=${BENCH_VM_DIR:-/media/rhy/data/bench-vms}
RAM=${BENCH_QEMU_RAM:-8192}
CPUS=${BENCH_QEMU_CPUS:-4}
DISK_SIZE=${BENCH_DISK_SIZE:-40G}
HTTP_PORT=${BENCH_HTTP_PORT:-8099}
VM_SSH_PORT=${BENCH_VM_SSH_PORT:-2240}
VNC_DISPLAY=${BENCH_VNC_DISPLAY:-121}
BOOT_TIMEOUT=${BENCH_ISO_BOOT_TIMEOUT:-300}
BOOT_MENU_TAPS=${BENCH_BOOT_MENU_TAPS:-3}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
HTTP_PID=''
VM_PID_FILE=''
CURRENT_VM_DIR=''

if [ $# -lt 2 ]; then
    usage
    exit 2
fi
OS=$1
RUN_LABEL=$2
shift 2
SUSPECT=''
NO_SSH_IDLE=0
WAIT_UNTIL=180
WINDOW=60
while [ $# -gt 0 ]; do
    case "$1" in
        --suspect) SUSPECT=$2; shift 2 ;;
        --no-ssh-idle) NO_SSH_IDLE=1; shift ;;
        --wait-until) WAIT_UNTIL=$2; shift 2 ;;
        --window) WINDOW=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

if [[ ! "$OS" =~ ^[A-Za-z0-9._-]+$ ]] || [[ ! "$RUN_LABEL" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "os-label and run-label must match [A-Za-z0-9._-]+" >&2
    exit 2
fi
for value in "$RAM" "$CPUS" "$HTTP_PORT" "$VM_SSH_PORT" "$VNC_DISPLAY" \
             "$BOOT_TIMEOUT" "$WAIT_UNTIL" "$WINDOW"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric setting: $value" >&2; exit 2; }
done

# Resolve the ISO and its access options from the matrix, exactly as the
# sweep runner reads them.
iso=''
access=qmp
terminal='ctrl-alt-t'
fetch=wget
while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in ''|'#'*) continue ;; esac
    label=${line%% *}
    [ "$label" = "$OS" ] || continue
    rest=${line#* }
    iso=${rest%% *}
    opts=${rest#* }
    [ "$opts" = "$rest" ] && opts=''
    iso=${iso//\{VERSION\}/$SPACED_VERSION}
    case "$iso" in /*) ;; *) iso="$PROJECT_ROOT/$iso" ;; esac
    for opt in $opts; do
        key=${opt%%=*}
        value=${opt#*=}
        value=${value//\{VERSION\}/$SPACED_VERSION}
        case "$key" in
            access) access=$value ;;
            terminal) terminal=$value ;;
            fetch) fetch=$value ;;
        esac
    done
done < "$MATRIX"
if [ -z "$iso" ]; then
    echo "SKIP: no matrix entry for $OS in $MATRIX" >&2
    exit 1
fi
if [ ! -f "$iso" ]; then
    echo "SKIP: no iso at $iso" >&2
    exit 1
fi
if [ "$access" != ssh ] && [ $NO_SSH_IDLE -eq 1 ]; then
    echo "SKIP: --no-ssh-idle needs an access=ssh guest" >&2
    exit 1
fi

STEM=idle-$OS-$RUN_LABEL
mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)
PUB=$OUT_DIR/$STEM-pub
INBOX=$OUT_DIR/$STEM-inbox
SAMPLER=$PUB/$OS/sampler.py
rm -rf "$PUB" "$INBOX"
mkdir -p "$PUB/$OS" "$INBOX/$OS"

# The guest sampler: python3 stdlib on every distro in the matrix (the
# bootstrap already fetches through python3). It reads /proc only, writes
# nothing big, and posts its two small result files back over HTTP.
cat > "$SAMPLER" <<'PY'
#!/usr/bin/env python3
"""Idle sampler for task b02: who uses the CPU and the context switches?

Waits for the uptime, then over one window records per-process CPU ticks and
context-switch deltas from /proc, the /proc/stat totals over the SAME window
(the same cpu in-use formula as scripts/vm/bench/guest-probe.sh) and
/proc/interrupts deltas. Writes <prefix>.tsv and <prefix>-totals.txt; with
--post they are also POSTed to the host collector.
"""
import argparse
import glob
import os
import time
import urllib.request


def read_cpu():
    with open('/proc/stat', encoding='ascii') as handle:
        for line in handle:
            if line.startswith('cpu '):
                return [int(v) for v in line.split()[1:]]
    raise SystemExit('no cpu line in /proc/stat')


def read_stat(name):
    with open('/proc/stat', encoding='ascii') as handle:
        for line in handle:
            parts = line.split()
            if parts and parts[0] == name:
                return int(parts[1])
    return None


def read_interrupts():
    out = {}
    try:
        with open('/proc/interrupts', encoding='ascii') as handle:
            lines = handle.read().splitlines()
    except OSError:
        return out
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        total = 0
        for token in parts[1:]:
            if token.isdigit():
                total += int(token)
        out[parts[0].rstrip(':')] = total
    return out


def read_procs():
    out = {}
    for path in glob.glob('/proc/[0-9]*'):
        pid = os.path.basename(path)
        try:
            with open(path + '/stat', encoding='ascii') as handle:
                stat = handle.read()
            comm = stat[stat.index('(') + 1:stat.rindex(')')]
            after = stat.rsplit(') ', 1)[1].split()
            utime = int(after[11])
            stime = int(after[12])
            vol = nonvol = 0
            try:
                with open(path + '/status', encoding='ascii') as handle:
                    for line in handle:
                        if line.startswith('voluntary_ctxt_switches:'):
                            vol = int(line.split()[1])
                        elif line.startswith('nonvoluntary_ctxt_switches:'):
                            nonvol = int(line.split()[1])
            except OSError:
                pass
            try:
                with open(path + '/cmdline', encoding='ascii') as handle:
                    args = handle.read().replace('\0', ' ').strip()[:80]
            except OSError:
                args = ''
            out[pid] = (comm, utime, stime, vol, nonvol, args)
        except (OSError, ValueError, IndexError):
            continue
    return out


def post(base, leaf, body):
    if not base:
        return
    try:
        request = urllib.request.Request(base + '/' + leaf,
                                         data=body.encode('utf-8'))
        urllib.request.urlopen(request, timeout=60).read()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--os', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--out-prefix', required=True)
    parser.add_argument('--post', default='')
    parser.add_argument('--wait-until', type=float, default=180)
    parser.add_argument('--window', type=float, default=60)
    args = parser.parse_args()

    uptime = float(open('/proc/uptime', encoding='ascii').read().split()[0])
    if uptime < args.wait_until:
        time.sleep(args.wait_until - uptime)
    post(args.post, 'started', 'ok')

    hz = os.sysconf('SC_CLK_TCK')
    uptime0 = float(open('/proc/uptime', encoding='ascii').read().split()[0])
    cpu0 = read_cpu()
    ctxt0 = read_stat('ctxt')
    intr0 = read_stat('intr')
    ints0 = read_interrupts()
    procs0 = read_procs()
    started = time.monotonic()
    time.sleep(args.window)
    elapsed = time.monotonic() - started
    cpu1 = read_cpu()
    ctxt1 = read_stat('ctxt')
    intr1 = read_stat('intr')
    ints1 = read_interrupts()
    procs1 = read_procs()

    total = sum(b - a for a, b in zip(cpu0, cpu1))
    # Same fields as the probe: idle (field 4) and iowait (field 5).
    idle = sum(cpu1[i] - cpu0[i] for i in (3, 4) if i < len(cpu0))
    cpu_in_use = 100.0 * (total - idle) / total if total > 0 else 0.0

    rows = []
    for pid in set(procs0) | set(procs1):
        a = procs0.get(pid, ('', 0, 0, 0, 0, ''))
        b = procs1.get(pid, (a[0], a[1], a[2], a[3], a[4], a[5]))
        ticks = (b[1] + b[2]) - (a[1] + a[2])
        switches = (b[3] + b[4]) - (a[3] + a[4])
        rows.append((int(pid), b[0] or a[0], 100.0 * ticks / (hz * elapsed),
                     switches / elapsed, b[5] or a[5]))
    rows.sort(key=lambda row: -row[2])

    tsv = '%s.tsv' % args.out_prefix
    totals = '%s-totals.txt' % args.out_prefix
    with open(tsv, 'w', encoding='utf-8') as handle:
        handle.write('pid\tcomm\tcpu_pct\tctxt_per_s\targs\n')
        for pid, comm, cpu_pct, per_s, args_line in rows:
            handle.write('%d\t%s\t%.2f\t%.1f\t%s\n'
                         % (pid, comm, cpu_pct, per_s, args_line))
    sum_pct = sum(row[2] for row in rows)
    int_delta = sorted(((k, ints1.get(k, 0) - ints0.get(k, 0))
                        for k in set(ints0) | set(ints1)),
                       key=lambda kv: -kv[1])[:5]
    with open(totals, 'w', encoding='utf-8') as handle:
        handle.write('uptime_at_sample %.1f\n' % uptime0)
        handle.write('cpu_in_use_pct %.2f\n' % cpu_in_use)
        handle.write('ctxt_per_s %.1f\n'
                     % ((ctxt1 - ctxt0) / elapsed
                        if ctxt0 is not None and ctxt1 is not None else 0))
        handle.write('intr_per_s %.1f\n'
                     % ((intr1 - intr0) / elapsed
                        if intr0 is not None and intr1 is not None else 0))
        handle.write('sum_of_process_cpu_pct %.1f\n' % sum_pct)
        handle.write('top_interrupts %s\n'
                     % ' '.join('%s:+%d' % (k, v) for k, v in int_delta))
    leaf = 'idle-%s-%s' % (args.os, args.label)
    post(args.post, leaf + '.tsv', open(tsv, encoding='utf-8').read())
    post(args.post, leaf + '-totals.txt',
         open(totals, encoding='utf-8').read())
    post(args.post, leaf + '.done', 'ok')


main()
PY

guest_ssh() {
    SSHPASS=$ROOT_PASSWORD sshpass -e ssh -p "$VM_SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

ssh_is_ready() {
    local banner=
    if ! exec 3<>"/dev/tcp/127.0.0.1/$VM_SSH_PORT" 2>/dev/null; then
        return 1
    fi
    IFS= read -r -t 2 banner <&3 || true
    exec 3<&-
    exec 3>&-
    [[ "$banner" == SSH-* ]]
}

stop_vm() {
    if [ -n "$VM_PID_FILE" ] && [ -f "$VM_PID_FILE" ]; then
        local pid
        pid=$(cat "$VM_PID_FILE" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            for _ in {1..20}; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.2
            done
            kill -KILL "$pid" 2>/dev/null || true
        fi
        rm -f "$VM_PID_FILE"
    fi
    VM_PID_FILE=''
}

cleanup() {
    stop_vm
    if [ -n "$HTTP_PID" ] && kill -0 "$HTTP_PID" 2>/dev/null; then
        kill "$HTTP_PID" 2>/dev/null || true
        wait "$HTTP_PID" 2>/dev/null || true
    fi
    if [ -n "$CURRENT_VM_DIR" ]; then
        rm -rf "$CURRENT_VM_DIR"
        CURRENT_VM_DIR=''
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Same fresh-VM rules as run-bench.sh: disk under BENCH_VM_DIR/<os>/, gone
# with the VM, nothing written outside build/bench and that directory.
if ! df -BG --output=avail "$(dirname "$VM_DIR_ROOT")" 2>/dev/null \
    | tail -n 1 | tr -dc '0-9' | grep -qE '[0-9]'; then
    echo "REFUSED: cannot read free space under $VM_DIR_ROOT" >&2
    exit 1
fi
vm_dir=$VM_DIR_ROOT/$OS
rm -rf "$vm_dir"
mkdir -p "$vm_dir"
CURRENT_VM_DIR=$vm_dir
if ! qemu-img create -f qcow2 "$vm_dir/disk.qcow2" "$DISK_SIZE" >/dev/null; then
    echo "SKIP: could not create $vm_dir/disk.qcow2" >&2
    exit 1
fi

qmp_sock=$OUT_DIR/$STEM.qmp
iso_log=$OUT_DIR/$STEM.qemu.log
VM_PID_FILE=$OUT_DIR/$STEM.qemu.pid
rm -f "$qmp_sock"

export SPACED_QEMU_RAM=$RAM SPACED_QEMU_CPUS=$CPUS VM_SSH_PORT
build_common_args
echo "BOOT: $OS label=$RUN_LABEL ($RAM MiB, $CPUS CPUs, KVM, $DISK_SIZE disk" \
    "under $vm_dir, VNC 127.0.0.1:$VNC_DISPLAY, QMP $qmp_sock, headless)"
if ! qemu-system-x86_64 "${QEMU_COMMON[@]}" \
    -drive "file=$vm_dir/disk.qcow2,if=virtio,format=qcow2" \
    -cdrom "$iso" -boot order=cdn \
    -vga std -display none -vnc "127.0.0.1:$VNC_DISPLAY" \
    -qmp "unix:$qmp_sock,server=on,wait=off" \
    -serial "file:$OUT_DIR/$STEM.serial.log" \
    -name "$OS" > "$iso_log" 2>&1 \
    -daemonize -pidfile "$VM_PID_FILE"; then
    echo "SKIP: qemu refused to start; see $iso_log" >&2
    exit 1
fi

python3 "$SCRIPT_DIR/http-report.py" --pub "$PUB" --in "$INBOX" \
    --port "$HTTP_PORT" --logfile "$OUT_DIR/$STEM-http.log" \
    > "$OUT_DIR/$STEM-http.out" 2>&1 &
HTTP_PID=$!
sleep 1

vm_alive() {
    local pid
    pid=$(cat "$VM_PID_FILE" 2>/dev/null || true)
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# One typed command starts the sampler over QMP (access=qmp distros have no
# SSH server): fetch the sampler, then run it detached, posting home.
typed_fetch() {
    local url=http://10.0.2.2:$HTTP_PORT/$OS/sampler.py
    case "$fetch" in
        curl) printf 'curl -sf %s -o /tmp/ii.py' "$url" ;;
        python3)
            printf 'python3 -c %s > /tmp/ii.py' \
                "'import sys,urllib.request;sys.stdout.buffer.write(urllib.request.urlopen(\"$url\").read())'"
            ;;
        *) printf 'wget -qO /tmp/ii.py %s' "$url" ;;
    esac
}

typed_run() {
    printf 'nohup python3 /tmp/ii.py --os %s --label %s --out-prefix /tmp/ii-%s --post http://10.0.2.2:%s/%s --wait-until %s --window %s >/tmp/ii-%s.log 2>&1 </dev/null & exit' \
        "$OS" "$RUN_LABEL" "$RUN_LABEL" "$HTTP_PORT" "$OS" \
        "$WAIT_UNTIL" "$WINDOW" "$RUN_LABEL"
}

open_terminal() {
    local recipe=$1 combo command
    combo=${recipe%%+*}
    command=${recipe#*+}
    python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" combo "$combo" \
        || return 1
    sleep 2
    if [ "$command" != "$recipe" ]; then
        python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" type "$command" \
            || return 1
        python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" key ret || return 1
        sleep 2
    fi
    return 0
}

# Reach the guest the way run-bench.sh does.
ready=no
started=$SECONDS
attempt=0
next_try=$((SECONDS + 8))
while (( SECONDS - started < BOOT_TIMEOUT )); do
    if ! vm_alive; then
        echo "SKIP: the VM exited while booting; see $iso_log" >&2
        exit 1
    fi
    if [ "$access" = ssh ]; then
        if ssh_is_ready && guest_ssh 'printf ok' >/dev/null 2>&1; then
            ready=ssh
            break
        fi
    elif [ -f "$INBOX/$OS/started" ]; then
        ready=qmp
        break
    fi
    if (( SECONDS >= next_try )); then
        attempt=$((attempt + 1))
        if (( attempt <= BOOT_MENU_TAPS )); then
            echo "BOOT: tapping Enter at the boot menu (attempt $attempt)"
            tapped=0
            while [ "$tapped" -lt 3 ]; do
                python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" key ret \
                    || true
                sleep 2
                tapped=$((tapped + 1))
            done
            next_try=$((SECONDS + 15))
        else
            echo "TRY: terminal recipe set attempt $attempt"
            IFS=';' read -ra recipes <<< "$terminal"
            for recipe in "${recipes[@]}"; do
                open_terminal "$recipe" || true
                python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" \
                    type "$(typed_fetch)" || true
                python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" key ret \
                    || true
                sleep 2
                python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" \
                    type "$(typed_run)" || true
                python3 "$SCRIPT_DIR/qmp-type.py" --qmp "$qmp_sock" key ret \
                    || true
                [ -f "$INBOX/$OS/started" ] && break
            done
            next_try=$((SECONDS + 30))
        fi
    fi
    echo "WAIT: $OS desktop via $access ($((SECONDS - started))s/$BOOT_TIMEOUT)"
    sleep 3
done
if [ "$ready" = no ]; then
    echo "SKIP: $OS desktop never reached within ${BOOT_TIMEOUT}s" >&2
    exit 1
fi
echo "READY: $OS via $access after $((SECONDS - started))s"

if [ "$access" = ssh ]; then
    if [ -n "$SUSPECT" ]; then
        echo "SUSPECT: $SUSPECT"
        guest_ssh "$SUSPECT" || echo "NOTE: suspect command returned non-zero"
        sleep 2
    fi
    sampler_args="python3 - --os $OS --label $RUN_LABEL --out-prefix /tmp/ii-$RUN_LABEL --post http://10.0.2.2:$HTTP_PORT/$OS --wait-until $WAIT_UNTIL --window $WINDOW"
    if [ "$NO_SSH_IDLE" = 1 ]; then
        # The sampler runs detached; the SSH session closes before the
        # window starts, so an open session cannot be what is measured.
        guest_ssh "cat > /tmp/ii-$RUN_LABEL.py" < "$SAMPLER"
        guest_ssh "nohup python3 /tmp/ii-$RUN_LABEL.py --os $OS --label $RUN_LABEL --out-prefix /tmp/ii-$RUN_LABEL --post http://10.0.2.2:$HTTP_PORT/$OS --wait-until $WAIT_UNTIL --window $WINDOW >/tmp/ii-$RUN_LABEL.log 2>&1 </dev/null & exit"
        echo "RUN: sampler detached with nohup, SSH session closed"
    else
        echo "RUN: sampler over the open SSH session"
        guest_ssh "$sampler_args" < "$SAMPLER"
    fi
fi

# Wait for the posted results: guest uptime wait + window + boot slack.
cap=$((WAIT_UNTIL + WINDOW + 300))
end=$((SECONDS + cap))
while [ $SECONDS -lt $end ]; do
    if [ -f "$INBOX/$OS/idle-$OS-$RUN_LABEL.done" ]; then
        break
    fi
    if ! vm_alive; then
        echo "SKIP: the VM exited before reporting; see $iso_log" >&2
        exit 1
    fi
    sleep 5
done
tsv=$OUT_DIR/$STEM.tsv
totals=$OUT_DIR/$STEM-totals.txt
if [ -f "$INBOX/$OS/idle-$OS-$RUN_LABEL.done" ]; then
    cp "$INBOX/$OS/idle-$OS-$RUN_LABEL.tsv" "$tsv"
    cp "$INBOX/$OS/idle-$OS-$RUN_LABEL-totals.txt" "$totals"
elif [ "$access" = ssh ] && vm_alive \
    && guest_ssh "cat /tmp/ii-$RUN_LABEL.tsv" > "$tsv" \
    && guest_ssh "cat /tmp/ii-$RUN_LABEL-totals.txt" > "$totals" \
    && [ -s "$totals" ]; then
    # The window ran but the HTTP post never landed; the files are still
    # small enough to cat back over the same SSH shell the runner used.
    echo "NOTE: results not posted; rescued from the guest over SSH"
else
    echo "SKIP: $STEM results never posted (cap ${cap}s)" >&2
    exit 1
fi
{
    printf 'ran_os %s\n' "$OS"
    printf 'ran_label %s\n' "$RUN_LABEL"
    printf 'access %s\n' "$access"
    if [ -n "$SUSPECT" ]; then
        printf 'suspect_cmd %s\n' "$SUSPECT"
    else
        printf 'suspect_cmd none\n'
    fi
    if [ "$NO_SSH_IDLE" = 1 ]; then
        printf 'ssh_open_during_sample no\n'
    elif [ "$access" = ssh ]; then
        printf 'ssh_open_during_sample yes\n'
    else
        printf 'ssh_open_during_sample no\n'
    fi
    printf 'host_load %s\n' "$(cut -d' ' -f1-3 /proc/loadavg)"
    if pgrep -x strata >/dev/null 2>&1; then
        printf 'strata_running yes\n'
    else
        printf 'strata_running no\n'
    fi
} >> "$totals"

echo "DONE: $OS label=$RUN_LABEL"
head -n 8 "$totals"
echo "TOP:"
head -n 9 "$tsv"
exit 0
