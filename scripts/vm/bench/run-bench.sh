#!/bin/bash
# Cross-OS benchmark runner: boots every ISO named in scripts/vm/bench/matrix.conf
# in KVM through scripts/vm/qemu/common.sh's build_common_args, copies
# scripts/vm/bench/guest-probe.sh into the guest over the forwarded SSH port,
# and writes one TSV row per OS under build/bench/.
#
# An entry whose ISO is not on this machine is reported as
# `SKIP: <label> no iso at <path>` and the run continues: a partial matrix is
# always visible, never hidden. The final `RESULT: measured=<n> skipped=<m>`
# line states what was actually measured, and the runner exits 0 even when
# every entry was skipped, because "no ISO here" is a fact, not a failure.
#
# Nothing is installed, no package manager is run on the host, and the only
# writes are under build/bench/. Spaced's own ISO is listed first in matrix.conf.
#
# Usage: run-bench.sh [MATRIX] [RUN-LABEL]
#   MATRIX      default scripts/vm/bench/matrix.conf
#   RUN-LABEL   names the TSV and log files (default 1)
#
# Environment: BENCH_VM_SSH_PORT (2240), BENCH_QEMU_RAM (4096),
# BENCH_QEMU_CPUS (4), BENCH_ISO_BOOT_TIMEOUT (300), BENCH_PROBE_IDLE_SECONDS
# (10), BENCH_SSH_POLL_SECONDS (2), BENCH_OUT_DIR.
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: run-bench.sh [MATRIX] [RUN-LABEL]

Boot each ISO in the matrix file in KVM, run guest-probe.sh inside it and write
one TSV row per OS to build/bench/<label>-<run>.tsv. Missing ISOs print
"SKIP: <label> no iso at <path>" and do not stop the run.

Environment: BENCH_VM_SSH_PORT (2240), BENCH_QEMU_RAM (4096),
BENCH_QEMU_CPUS (4), BENCH_ISO_BOOT_TIMEOUT (300), BENCH_PROBE_IDLE_SECONDS (10),
BENCH_SSH_POLL_SECONDS (2), BENCH_OUT_DIR.
USAGE
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
# shellcheck source=../qemu/common.sh
source "$SCRIPT_DIR/../qemu/common.sh"

MATRIX=${1:-$SCRIPT_DIR/matrix.conf}
RUN_LABEL=${2:-1}
PROBE=$SCRIPT_DIR/guest-probe.sh
VM_SSH_PORT=${BENCH_VM_SSH_PORT:-2240}
RAM=${BENCH_QEMU_RAM:-4096}
CPUS=${BENCH_QEMU_CPUS:-4}
BOOT_TIMEOUT=${BENCH_ISO_BOOT_TIMEOUT:-300}
IDLE_SECONDS=${BENCH_PROBE_IDLE_SECONDS:-10}
SSH_POLL=${BENCH_SSH_POLL_SECONDS:-2}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
OUT_DIR=${BENCH_OUT_DIR:-$PROJECT_ROOT/build/bench}

for value in "$VM_SSH_PORT" "$RAM" "$CPUS" "$BOOT_TIMEOUT" "$IDLE_SECONDS" "$SSH_POLL"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
if [[ ! "$RUN_LABEL" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Invalid run label: $RUN_LABEL" >&2
    exit 2
fi
if [ ! -f "$PROBE" ]; then
    echo "Probe script is missing: $PROBE" >&2
    exit 2
fi

measured=0
skipped=0

if [ ! -f "$MATRIX" ]; then
    echo "SKIP: matrix file not found: $MATRIX"
    echo "RESULT: measured=$measured skipped=$skipped"
    exit 0
fi

# The matrix is read before anything is booted, so a malformed line is reported
# without half a benchmark run having happened.
labels=()
isos=()
while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in
        ''|'#'*) continue ;;
    esac
    label=${line%% *}
    iso=${line#* }
    if [ "$iso" = "$line" ]; then
        echo "SKIP: $label no iso path given in $MATRIX"
        skipped=$((skipped + 1))
        continue
    fi
    # {VERSION} keeps the Spaced line correct across releases, and a relative
    # path is resolved against the repository root, never the caller's cwd.
    iso=${iso//\{VERSION\}/$SPACED_VERSION}
    case "$iso" in
        /*) ;;
        *) iso="$PROJECT_ROOT/$iso" ;;
    esac
    if [[ ! "$label" =~ ^[A-Za-z0-9._+-]+$ ]]; then
        echo "SKIP: $label invalid label in $MATRIX"
        skipped=$((skipped + 1))
        continue
    fi
    labels+=("$label")
    isos+=("$iso")
done < "$MATRIX"

if [ ${#labels[@]} -eq 0 ]; then
    echo "SKIP: matrix has no entries: $MATRIX"
    echo "RESULT: measured=$measured skipped=$skipped"
    exit 0
fi

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)
QEMU_PID=''

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    stop_vm
    [ -z "$QEMU_PID" ] || wait "$QEMU_PID" 2>/dev/null || true
}

stop_vm() {
    # QEMU is stopped by the PID in the pidfile this run wrote, never by name
    # matching, and only this runner's pidfile is touched.
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

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$VM_SSH_PORT" \
        -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null root@127.0.0.1 "$@"
}

guest_scp() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e scp -P "$VM_SSH_PORT" -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$@"
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

# Boots one ISO, runs the probe inside it and turns the INFO: lines into one
# TSV row. Returns non-zero when this OS could not be measured, so the caller
# counts it as skipped rather than as a silent gap.
measure_entry() {
    local label=$1 iso=$2 stem tsv probe_out iso_size
    stem="$label-$RUN_LABEL"
    tsv="$OUT_DIR/$stem.tsv"
    probe_out="$OUT_DIR/$stem-probe.txt"
    iso_size=$(stat -c %s "$iso")
    rm -f "$tsv" "$probe_out"
    VM_PID_FILE="$OUT_DIR/$stem.qemu.pid"

    build_common_args
    echo "Booting $label from $iso ($RAM MiB, $CPUS CPUs, KVM, SSH 127.0.0.1:$VM_SSH_PORT)"
    if ! qemu-system-x86_64 "${QEMU_COMMON[@]}" -vga std \
        -cdrom "$iso" -boot order=c -display none \
        -serial "file:$OUT_DIR/$stem.serial.log" \
        -daemonize -pidfile "$VM_PID_FILE"; then
        echo "SKIP: $label qemu refused to start; see $OUT_DIR/$stem.serial.log"
        return 1
    fi

    local started=$SECONDS ready=no
    while (( SECONDS - started < BOOT_TIMEOUT )); do
        if [ -f "$VM_PID_FILE" ] && ! kill -0 "$(cat "$VM_PID_FILE")" 2>/dev/null; then
            break
        fi
        if ssh_is_ready 2>/dev/null && guest_ssh 'printf ok' >/dev/null 2>&1; then
            ready=yes
            break
        fi
        echo "Waiting for $label SSH ($((SECONDS - started))s/${BOOT_TIMEOUT}s)"
        sleep "$SSH_POLL"
    done
    if [ "$ready" != yes ]; then
        echo "SKIP: $label no SSH on port $VM_SSH_PORT within ${BOOT_TIMEOUT}s"
        stop_vm
        return 1
    fi

    if ! guest_scp "$PROBE" root@127.0.0.1:/tmp/bench-guest-probe.sh; then
        echo "SKIP: $label could not copy the probe in over SSH"
        stop_vm
        return 1
    fi
    if ! guest_ssh "bash /tmp/bench-guest-probe.sh --idle $IDLE_SECONDS" \
        > "$probe_out" 2>&1; then
        echo "SKIP: $label probe failed in the guest; see $probe_out"
        stop_vm
        return 1
    fi
    grep -q '^INFO: ' "$probe_out" || {
        echo "SKIP: $label probe printed no metrics; see $probe_out"
        stop_vm
        return 1
    }

    if ! python3 - "$probe_out" "$tsv" "$label" "$RUN_LABEL" "$iso" "$iso_size" <<'PY'
import csv
import re
import sys

probe_out, tsv, label, run_label, iso, iso_size = sys.argv[1:7]
METRICS = (
    'uptime_at_desktop_ready_s',
    'mem_used_mib',
    'process_count',
    'top10_rss_kib',
    'context_switches_per_s',
    'interrupts_per_s',
    'idle_cpu_percent',
    'diskstats_reads_completed',
    'diskstats_sectors_read',
    'diskstats_mib_read',
    'pkg_manager',
    'package_count',
    'pkg_manager_query_ms',
)

values = {}
for line in open(probe_out, encoding='utf-8', errors='replace'):
    match = re.match(r'INFO: ([A-Za-z0-9_]+)=(.*)', line)
    if match:
        values[match.group(1)] = match.group(2).strip()

skipped = [name for name in METRICS if name not in values]
row = {'os_label': label, 'run_label': run_label, 'iso_path': iso,
       'iso_size_bytes': iso_size}
for name in METRICS:
    row[name] = values.get(name, '')

with open(tsv, 'w', encoding='utf-8', newline='') as handle:
    writer = csv.DictWriter(handle, ['os_label', 'run_label', 'iso_path',
                                    'iso_size_bytes'] + list(METRICS),
                            delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerow(row)

print('INFO: %s metrics=%d missing=%d' % (label, len(METRICS) - len(skipped),
                                          len(skipped)))
if skipped:
    print('INFO: %s missing_metrics=%s' % (label, ' '.join(skipped)))
PY
    then
        echo "SKIP: $label could not turn the probe output into a row"
        stop_vm
        return 1
    fi

    echo "MEASURED: $label row=$tsv"
    stop_vm
    return 0
}

for index in "${!labels[@]}"; do
    label=${labels[$index]}
    iso=${isos[$index]}
    if [ ! -f "$iso" ]; then
        echo "SKIP: $label no iso at $iso"
        skipped=$((skipped + 1))
        continue
    fi
    if measure_entry "$label" "$iso"; then
        measured=$((measured + 1))
    else
        skipped=$((skipped + 1))
    fi
done

echo "Artifacts: $OUT_DIR"
echo "RESULT: measured=$measured skipped=$skipped"
exit 0
