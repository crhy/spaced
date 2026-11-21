#!/bin/bash
# Cross-OS benchmark sweep for issue #424: Spaced Linux against the most
# popular distros, one FRESH VM per OS, destroyed when that OS finishes.
#
# Every entry in scripts/vm/bench/matrix.conf is booted in KVM with the exact
# same machine (-cpu host, 4 vCPU, 8 GiB, virtio disk 40G qcow2, user-mode
# virtio NIC, -display none, VNC on 127.0.0.1 only), headless, with its disk
# under /media/rhy/data/bench-vms/<label>/ which is deleted when the OS is
# done or failed. Nothing is ever written to /tmp or /home for the VMs, and
# the sweep refuses to start unless /media/rhy/data has enough room.
#
# Most live ISOs have no SSH server, so a guest is driven through QMP: the
# runner types one short command into the live desktop's terminal (the shortcut
# recorded per distro in matrix.conf) that fetches the probe and the setup
# script from a host HTTP server on 10.0.2.2 and posts every result back over
# HTTP. The Spaced ISO also answers SSH, and access=ssh uses that.
#
# Measured per OS: the f093 probe metrics (boot-to-desktop, idle RAM, idle
# CPU, processes, context switches, disk reads) plus a short Phoronix Test
# Suite set run inside the guest, capped per OS. Results are the probe's INFO
# lines, PTS's own result files, and one TSV row per OS in build/bench/.
# Host load and whether Strata was running are recorded in every row.
#
# A missing ISO or an OS that cannot be driven is reported, never hidden:
#   SKIP: <label> no iso at <path>
#   SKIP: <label> desktop never reached within <n>s
#   RESULT: measured=<n> skipped=<m>
# The exit status is 0 unless the arguments or the disk-free gate failed, so
# a partial matrix is a result, not a crash.
#
# Usage: run-bench.sh [MATRIX] [RUN-LABEL] [ONLY-LABELS]
#   MATRIX        default scripts/vm/bench/matrix.conf
#   RUN-LABEL     names the TSV and log files (default 1)
#   ONLY-LABELS   comma-separated labels to run (default every matrix entry)
#
# Environment: BENCH_VM_DIR (/media/rhy/data/bench-vms), BENCH_FREE_MIN_GB
# (15), BENCH_QEMU_RAM (8192), BENCH_QEMU_CPUS (4), BENCH_DISK_SIZE (40G),
# BENCH_OS_CAP_SECONDS (1200), BENCH_PROBE_IDLE_SECONDS (20), BENCH_HTTP_PORT
# (8099), BENCH_VM_SSH_PORT (2240), BENCH_VNC_DISPLAY (90), BENCH_ISO_BOOT_
# TIMEOUT (300), BENCH_SSH_POLL_SECONDS (2), BENCH_OUT_DIR.
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
Usage: run-bench.sh [MATRIX] [RUN-LABEL] [ONLY-LABELS]

Boot each ISO in the matrix file in a fresh KVM VM, measure it with
guest-probe.sh and a short Phoronix Test Suite set, write one TSV row per OS
to build/bench/<label>-<run>.tsv, and destroy the VM and its disk afterwards.
Missing ISOs print "SKIP: <label> no iso at <path>" and do not stop the run.

Environment: BENCH_VM_DIR (/media/rhy/data/bench-vms), BENCH_FREE_MIN_GB (15),
BENCH_QEMU_RAM (8192), BENCH_QEMU_CPUS (4), BENCH_DISK_SIZE (40G),
BENCH_OS_CAP_SECONDS (1200), BENCH_PROBE_IDLE_SECONDS (20), BENCH_HTTP_PORT
(8099), BENCH_VM_SSH_PORT (2240), BENCH_VNC_DISPLAY (90), BENCH_OUT_DIR.
USAGE
}

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)
# shellcheck source=../qemu/common.sh
source "$SCRIPT_DIR/../qemu/common.sh"

MATRIX=${1:-$SCRIPT_DIR/matrix.conf}
RUN_LABEL=${2:-1}
ONLY=${3:-}
PROBE=$SCRIPT_DIR/guest-probe.sh
BOOTSTRAP=$SCRIPT_DIR/guest-bootstrap.sh
GUEST_PTS=$SCRIPT_DIR/guest-pts.sh
QMP_TYPE=$SCRIPT_DIR/qmp-type.py
HTTP_REPORT=$SCRIPT_DIR/http-report.py

VM_DIR_ROOT=${BENCH_VM_DIR:-/media/rhy/data/bench-vms}
FREE_MIN_GB=${BENCH_FREE_MIN_GB:-15}
RAM=${BENCH_QEMU_RAM:-8192}
CPUS=${BENCH_QEMU_CPUS:-4}
DISK_SIZE=${BENCH_DISK_SIZE:-40G}
CAP_SECONDS=${BENCH_OS_CAP_SECONDS:-1200}
IDLE_SECONDS=${BENCH_PROBE_IDLE_SECONDS:-20}
HTTP_PORT=${BENCH_HTTP_PORT:-8099}
VM_SSH_PORT=${BENCH_VM_SSH_PORT:-2240}
VNC_BASE=${BENCH_VNC_DISPLAY:-90}
BOOT_TIMEOUT=${BENCH_ISO_BOOT_TIMEOUT:-300}
SSH_POLL=${BENCH_SSH_POLL_SECONDS:-2}
ROOT_PASSWORD=${SPACED_LIVE_ROOT_PASSWORD:-spaced}
OUT_DIR=${BENCH_OUT_DIR:-$PROJECT_ROOT/build/bench}

for value in "$HTTP_PORT" "$RAM" "$CPUS" "$CAP_SECONDS" "$IDLE_SECONDS" \
             "$VM_SSH_PORT" "$VNC_BASE" "$BOOT_TIMEOUT" "$SSH_POLL" \
             "$FREE_MIN_GB"; do
    [[ "$value" =~ ^[0-9]+$ ]] || { echo "Invalid numeric VM setting: $value" >&2; exit 2; }
done
if [[ ! "$RUN_LABEL" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Invalid run label: $RUN_LABEL" >&2
    exit 2
fi
for script in "$PROBE" "$BOOTSTRAP" "$GUEST_PTS" "$QMP_TYPE" "$HTTP_REPORT"; do
    if [ ! -f "$script" ]; then
        echo "Harness file is missing: $script" >&2
        exit 2
    fi
done

measured=0
skipped=0

if [ ! -f "$MATRIX" ]; then
    echo "SKIP: matrix file not found: $MATRIX"
    echo "RESULT: measured=$measured skipped=$skipped"
    exit 0
fi

# The matrix is read before anything is booted, so a malformed line is
# reported without half a benchmark run having happened.
#   <label> <iso-path> [distro=.. version=.. desktop=.. access=ssh|qmp
#                        terminal=.. rootcmd=.. fetch=wget|curl|python3]
labels=()
isos=()
distros=()
versions=()
desktops=()
accesses=()
terminals=()
rootcmds=()
fetches=()
while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in
        ''|'#'*) continue ;;
    esac
    label=${line%% *}
    rest=${line#* }
    if [ "$rest" = "$line" ]; then
        echo "SKIP: $label no iso path given in $MATRIX"
        skipped=$((skipped + 1))
        continue
    fi
    iso=${rest%% *}
    opts=${rest#* }
    [ "$opts" = "$rest" ] && opts=''
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
    distro=$label
    version=unknown
    desktop=unknown
    access=qmp
    terminal='ctrl-alt-t'
    rootcmd=none
    fetch=wget
    bad=0
    for opt in $opts; do
        key=${opt%%=*}
        value=${opt#*=}
        value=${value//\{VERSION\}/$SPACED_VERSION}
        case "$key" in
            distro) distro=$value ;;
            version) version=$value ;;
            desktop) desktop=${value//+/ } ;;
            access) access=$value ;;
            terminal) terminal=$value ;;
            rootcmd) rootcmd=${value//+/ } ;;
            fetch) fetch=$value ;;
            *)
                echo "SKIP: $label unknown matrix option: $opt"
                bad=1
                ;;
        esac
    done
    if [ "$bad" = 0 ] && [ "$access" != ssh ] && [ "$access" != qmp ]; then
        echo "SKIP: $label unknown access=$access (ssh or qmp)"
        bad=1
    fi
    if [ "$bad" = 0 ] && [ "$fetch" != wget ] && [ "$fetch" != curl ] \
        && [ "$fetch" != python3 ]; then
        echo "SKIP: $label unknown fetch=$fetch (wget, curl or python3)"
        bad=1
    fi
    if [ "$bad" = 1 ]; then
        skipped=$((skipped + 1))
        continue
    fi
    if [ -n "$ONLY" ] && [[ ",$ONLY," != *",$label,"* ]]; then
        continue
    fi
    labels+=("$label")
    isos+=("$iso")
    distros+=("$distro")
    versions+=("$version")
    desktops+=("$desktop")
    accesses+=("$access")
    terminals+=("$terminal")
    rootcmds+=("$rootcmd")
    fetches+=("$fetch")
done < "$MATRIX"

if [ ${#labels[@]} -eq 0 ]; then
    echo "SKIP: matrix has no entries: $MATRIX"
    echo "RESULT: measured=$measured skipped=$skipped"
    exit 0
fi

# The disk-free gate: the VMs boot live ISOs and their disks stay small, but
# 15 GB of room is the agreed minimum for one guest plus its logs.
free_gb() {
    df -BG --output=avail "$1" 2>/dev/null | tail -n 1 | tr -dc '0-9'
}

DATA_PARTITION=$(dirname "$VM_DIR_ROOT")
free_at_start=$(free_gb "$DATA_PARTITION")
if [ -z "$free_at_start" ] || (( free_at_start < FREE_MIN_GB )); then
    echo "REFUSED: ${free_at_start:-0} GB free on $DATA_PARTITION; the sweep needs at least ${FREE_MIN_GB} GB"
    echo "RESULT: measured=0 skipped=${#labels[@]}"
    exit 1
fi

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)
HTTP_PID=''
CURRENT_VM_DIR=''

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
    stop_vm
    stop_http
    if [ -n "$CURRENT_VM_DIR" ]; then
        rm -rf "$CURRENT_VM_DIR"
        CURRENT_VM_DIR=''
    fi
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

stop_http() {
    if [ -n "$HTTP_PID" ] && kill -0 "$HTTP_PID" 2>/dev/null; then
        kill "$HTTP_PID" 2>/dev/null || true
        wait "$HTTP_PID" 2>/dev/null || true
    fi
    HTTP_PID=''
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

guest_ssh() {
    SSHPASS="$ROOT_PASSWORD" sshpass -e ssh -p "$VM_SSH_PORT" \
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

strata_running() {
    # The fair-comparison note: Strata's own inference runs on this machine and
    # would skew numbers, so every row records whether it was up. pgrep matches
    # the engine by its own command name only, never by a pattern.
    if pgrep -x strata >/dev/null 2>&1; then
        echo yes
    else
        echo no
    fi
}

# Types one terminal recipe into the live desktop: "ctrl-alt-t" presses a
# shortcut, "alt-f2+xterm" opens a run dialog and types a command first.
open_terminal() {
    local recipe=$1 qmp=$2 combo command
    combo=${recipe%%+*}
    command=${recipe#*+}
    python3 "$QMP_TYPE" --qmp "$qmp" combo "$combo" || return 1
    sleep 2
    if [ "$command" != "$recipe" ]; then
        python3 "$QMP_TYPE" --qmp "$qmp" type "$command" || return 1
        python3 "$QMP_TYPE" --qmp "$qmp" key ret || return 1
        sleep 2
    fi
    return 0
}

# Generates this OS's bootstrap: the config the guest scripts need, then the
# shared bootstrap piped through sh. The typed command stays deliberately
# short; everything else arrives over HTTP.
write_bootstrap() {
    local label=$1 distro=$2 rootcmd=$3 fetch=$4 pub=$5
    {
        echo "LABEL=$label"
        echo "DISTRO=$distro"
        echo "HOST=10.0.2.2"
        echo "PORT=$HTTP_PORT"
        echo "IDLE_SECONDS=$IDLE_SECONDS"
        echo "CAP_SECONDS=$CAP_SECONDS"
        echo "SUDO='$rootcmd'"
        echo "FETCH_TOOL=$fetch"
        echo "PTS_TESTS='pts/compress-zstd pts/sqlite-speedtest pts/openssl'"
        cat "$BOOTSTRAP"
    } > "$pub/$label/b.sh"
}

typed_bootstrap_command() {
    # The one command typed into the terminal: fetch this OS's bootstrap and
    # run it. 10.0.2.2 is the host in QEMU's user-mode network. wget ships on
    # every live desktop here; curl is typed instead where the distro has it.
    local label=$1 fetch=$2
    local url=http://10.0.2.2:$HTTP_PORT/$label/b.sh
    if [ "$fetch" = curl ]; then
        printf 'curl -s %s | sh' "$url"
    else
        printf 'wget -qO- %s | sh' "$url"
    fi
}

# Boots one ISO, measures it and writes one TSV row. Returns non-zero when
# this OS could not be measured, so the caller counts it as skipped.
measure_entry() {
    local index=$1
    local label=${labels[$index]} iso=${isos[$index]} distro=${distros[$index]}
    local version=${versions[$index]} desktop=${desktops[$index]}
    local access=${accesses[$index]} terminal=${terminals[$index]}
    local rootcmd=${rootcmds[$index]} fetch=${fetches[$index]}
    local stem tsv iso_size vm_dir qmp_sock pub inbox iso_log vnc_display
    stem="$label-$RUN_LABEL"
    tsv="$OUT_DIR/$stem.tsv"
    iso_size=$(stat -c %s "$iso")
    rm -f "$tsv" "$OUT_DIR/$stem-probe.txt" "$OUT_DIR/$stem-pts.tsv"

    # One FRESH VM per OS, on the data partition only, never /tmp, never /home.
    vm_dir="$VM_DIR_ROOT/$label"
    rm -rf "$vm_dir"
    mkdir -p "$vm_dir"
    CURRENT_VM_DIR=$vm_dir
    if ! qemu-img create -f qcow2 "$vm_dir/disk.qcow2" "$DISK_SIZE" >/dev/null; then
        echo "SKIP: $label could not create $vm_dir/disk.qcow2"
        return 1
    fi

    pub="$OUT_DIR/$stem-pub"
    inbox="$OUT_DIR/$stem-inbox"
    rm -rf "$pub" "$inbox"
    mkdir -p "$pub/$label" "$inbox/$label"
    cp "$PROBE" "$pub/guest-probe.sh"
    cp "$GUEST_PTS" "$pub/guest-pts.sh"
    write_bootstrap "$label" "$distro" "$rootcmd" "$fetch" "$pub"
    iso_log="$OUT_DIR/$stem.qemu.log"
    qmp_sock="$OUT_DIR/$stem.qmp"
    VM_PID_FILE="$OUT_DIR/$stem.qemu.pid"
    vnc_display=$((VNC_BASE + index))
    rm -f "$qmp_sock"

    export SPACED_QEMU_RAM=$RAM SPACED_QEMU_CPUS=$CPUS VM_SSH_PORT
    build_common_args
    echo "Booting $label from $iso ($RAM MiB, $CPUS CPUs, KVM, virtio disk" \
         "$DISK_SIZE under $vm_dir, VNC 127.0.0.1:$vnc_display," \
         "QMP $qmp_sock, headless)"
    if ! qemu-system-x86_64 "${QEMU_COMMON[@]}" \
        -drive "file=$vm_dir/disk.qcow2,if=virtio,format=qcow2" \
        -cdrom "$iso" -boot order=cdn \
        -vga std -display none -vnc "127.0.0.1:$vnc_display" \
        -qmp "unix:$qmp_sock,server=on,wait=off" \
        -serial "file:$OUT_DIR/$stem.serial.log" \
        -name "$label" > "$iso_log" 2>&1 \
        -daemonize -pidfile "$VM_PID_FILE"; then
        echo "SKIP: $label qemu refused to start; see $iso_log"
        return 1
    fi
    python3 "$HTTP_REPORT" --pub "$pub" --in "$inbox" --port "$HTTP_PORT" \
        --logfile "$OUT_DIR/$stem-http.log" > "$OUT_DIR/$stem-http.out" 2>&1 &
    HTTP_PID=$!
    sleep 1

    local started=$SECONDS boot_ready=no desktop_s=unknown attempt=0
    local next_try=$((SECONDS + 15)) command
    command=$(typed_bootstrap_command "$label" "$fetch")
    # Live ISO boot menus wait for a keyboard: send Enter so the default entry
    # starts, and keep doing it while the ISO is still booting (harmless once
    # the desktop is up, because the keystrokes are the bootstrap command).
    while (( SECONDS - started < BOOT_TIMEOUT )); do
        if [ -f "$VM_PID_FILE" ] && ! kill -0 "$(cat "$VM_PID_FILE")" 2>/dev/null; then
            echo "SKIP: $label the VM exited while booting; see $iso_log"
            return 1
        fi
        if [ -f "$inbox/$label/beacon" ]; then
            boot_ready=qmp
            desktop_s=$((SECONDS - started))
            break
        fi
        if [ "$access" = ssh ] && ssh_is_ready 2>/dev/null \
            && guest_ssh 'printf ok' >/dev/null 2>&1; then
            boot_ready=ssh
            desktop_s=$((SECONDS - started))
            break
        fi
        if (( SECONDS >= next_try )); then
            attempt=$((attempt + 1))
            echo "TRY: $label terminal recipe set attempt $attempt"
            local recipe
            IFS=";" read -ra recipes <<< "$terminal"
            for recipe in "${recipes[@]}"; do
                open_terminal "$recipe" "$qmp_sock" || true
                python3 "$QMP_TYPE" --qmp "$qmp_sock" type "$command" || true
                python3 "$QMP_TYPE" --qmp "$qmp_sock" key ret || true
                local waited=0
                while [ $waited -lt 12 ] && [ ! -f "$inbox/$label/beacon" ]; do
                    sleep 2
                    waited=$((waited + 2))
                done
                [ -f "$inbox/$label/beacon" ] && break
            done
            next_try=$((SECONDS + 30))
        fi
        echo "Waiting for $label desktop ($((SECONDS - started))s/${BOOT_TIMEOUT}s, attempt $attempt)"
        sleep 3
    done
    if [ "$boot_ready" = no ]; then
        python3 "$QMP_TYPE" --qmp "$qmp_sock" screen \
            "$OUT_DIR/$stem-last-screen.ppm" >/dev/null 2>&1 || true
        echo "SKIP: $label desktop never reached within ${BOOT_TIMEOUT}s"
        return 1
    fi
    echo "READY: $label via $boot_ready after ${desktop_s}s"

    if [ "$boot_ready" = ssh ]; then
        # The Spaced ISO answers root SSH; run the very same bootstrap there so
        # both access routes produce the same artifacts.
        if ! guest_ssh "sh -s" < "$pub/$label/b.sh" \
            > "$OUT_DIR/$stem-ssh-bootstrap.log" 2>&1; then
            echo "NOTE: $label bootstrap over SSH returned non-zero; see" \
                 "$OUT_DIR/$stem-ssh-bootstrap.log"
        fi
    fi

    # The guest posts probe output, PTS rows and its own result files; wait for
    # the done marker or the per-OS cap, whichever comes first.
    local deadline=$((started + CAP_SECONDS))
    while [ $SECONDS -lt $deadline ]; do
        [ -f "$inbox/$label/done" ] && break
        if [ -f "$VM_PID_FILE" ] && ! kill -0 "$(cat "$VM_PID_FILE")" 2>/dev/null; then
            echo "NOTE: $label the VM exited before reporting everything"
            break
        fi
        sleep 5
    done
    python3 "$QMP_TYPE" --qmp "$qmp_sock" screen \
        "$OUT_DIR/$stem-end-screen.ppm" >/dev/null 2>&1 || true

    if [ ! -f "$inbox/$label/probe.txt" ]; then
        echo "SKIP: $label probe never reported; see $OUT_DIR/$stem-http.log"
        return 1
    fi
    cp "$inbox/$label/probe.txt" "$OUT_DIR/$stem-probe.txt"
    [ -f "$inbox/$label/pts.tsv" ] &&
        cp "$inbox/$label/pts.tsv" "$OUT_DIR/$stem-pts.tsv"
    [ -f "$inbox/$label/pts-results.tar" ] &&
        cp "$inbox/$label/pts-results.tar" "$OUT_DIR/$stem-pts-results.tar"

    local probe_s=$((SECONDS - started))
    if ! python3 - "$inbox" "$tsv" "$label" "$RUN_LABEL" "$iso" "$iso_size" \
        "$distro" "$version" "$desktop" "$boot_ready" "$desktop_s" \
        "$probe_s" "$CAP_SECONDS" <<'PY'
import csv
import os
import re
import sys

(inbox, tsv, label, run_label, iso, iso_size, distro, version, desktop,
 access, desktop_s, probe_s, cap) = sys.argv[1:14]
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
probe_path = os.path.join(inbox, label, 'probe.txt')
for line in open(probe_path, encoding='utf-8', errors='replace'):
    match = re.match(r'INFO: ([A-Za-z0-9_]+)=(.*)', line)
    if match:
        values[match.group(1)] = match.group(2).strip()

pts = {}
pts_path = os.path.join(inbox, label, 'pts.tsv')
if os.path.isfile(pts_path):
    rows = [line.rstrip('\n').split('\t')
            for line in open(pts_path, encoding='utf-8', errors='replace')]
    pts['pts_tests'] = str(max(0, len(rows) - 1))
    statuses = [row[-1] for row in rows[1:] if len(row) >= 6]
    pts['pts_status'] = ';'.join(sorted(set(statuses)))[:200]
    times = [row[3] for row in rows[1:]
             if len(row) >= 6 and row[2] == 'test-total-time']
    try:
        pts['pts_total_time_s'] = '%.1f' % sum(float(t) for t in times)
    except ValueError:
        pts['pts_total_time_s'] = ''
status_path = os.path.join(inbox, label, 'pts-status')
if os.path.isfile(status_path):
    for line in open(status_path, encoding='utf-8', errors='replace'):
        match = re.match(r'(pts_[a-z_]+)=(.*)', line)
        if match:
            pts[match.group(1)] = match.group(2).strip()

try:
    load = ' '.join(open('/proc/loadavg', encoding='utf-8').read().split()[:3])
except OSError:
    load = ''
import subprocess
strata = subprocess.run(['pgrep', '-x', 'strata'], capture_output=True)

columns = (['os_label', 'run_label', 'iso_path', 'iso_size_bytes',
            'distro', 'version', 'desktop', 'access', 'iso_boot_menu_s',
            'boot_to_desktop_s', 'probe_window_s', 'cap_seconds',
            'host_load_at_row', 'strata_running']
           + list(METRICS)
           + ['pts_tests', 'pts_status', 'pts_total_time_s',
              'pts_install', 'pts_seconds'])
row = {'os_label': label, 'run_label': run_label, 'iso_path': iso,
       'iso_size_bytes': iso_size, 'distro': distro, 'version': version,
       'desktop': desktop, 'access': access, 'iso_boot_menu_s': '',
       'boot_to_desktop_s': desktop_s, 'probe_window_s': probe_s,
       'cap_seconds': cap, 'host_load_at_row': load,
       'strata_running': 'yes' if strata.returncode == 0 else 'no'}
for name in METRICS:
    row[name] = values.get(name, '')
for name, value in pts.items():
    row[name] = value

with open(tsv, 'w', encoding='utf-8', newline='') as handle:
    writer = csv.DictWriter(handle, columns, delimiter='\t',
                            lineterminator='\n', restval='',
                            extrasaction='ignore')
    writer.writeheader()
    writer.writerow(row)

missing = [name for name in METRICS if name not in values]
print('INFO: %s metrics=%d missing=%d' % (label, len(METRICS) - len(missing),
                                          len(missing)))
if missing:
    print('INFO: %s missing_metrics=%s' % (label, ' '.join(missing)))
PY
    then
        echo "SKIP: $label could not turn the probe output into a row"
        return 1
    fi

    echo "MEASURED: $label row=$tsv"
    return 0
}

destroy_entry() {
    # The VM and its whole disk are gone before the next OS starts.
    stop_vm
    stop_http
    if [ -n "$CURRENT_VM_DIR" ]; then
        rm -rf "$CURRENT_VM_DIR"
        CURRENT_VM_DIR=''
    fi
    local free_after
    free_after=$(free_gb "$DATA_PARTITION")
    echo "DESTROYED: ${labels[$1]} disk gone, ${free_after:-?} GB free on $DATA_PARTITION"
}

for index in "${!labels[@]}"; do
    label=${labels[$index]}
    iso=${isos[$index]}
    if [ ! -f "$iso" ]; then
        echo "SKIP: $label no iso at $iso"
        skipped=$((skipped + 1))
        continue
    fi
    if measure_entry "$index"; then
        measured=$((measured + 1))
    else
        skipped=$((skipped + 1))
    fi
    destroy_entry "$index"
done

echo "Artifacts: $OUT_DIR"
echo "RESULT: measured=$measured skipped=$skipped"
exit 0
