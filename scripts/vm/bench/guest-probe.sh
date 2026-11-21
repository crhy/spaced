#!/bin/bash
# OS-agnostic benchmark probe: prints INFO: <metric>=<value> lines for the
# machine it runs on, using the same metric names scripts/vm/qemu/release-measure.sh
# reports, so one Spaced run and one Debian run land in the same TSV columns.
#
# It reads /proc and its own clock only: no package installs, no writes, no
# network, no root, no display, nothing Spaced-specific. A metric a distro
# cannot provide (no /proc, no /proc/interrupts, no package manager) is reported
# as `SKIP: <metric> not available on this distro` instead of a guessed number.
#
# Metrics:
#   uptime_at_desktop_ready_s  /proc/uptime when the probe reaches ready
#   mem_used_mib               /proc/meminfo, free(1)'s used column
#   process_count              entries under /proc/[0-9]*
#   top10_rss_kib              sum of the 10 largest VmRSS values
#   context_switches_per_s     /proc/stat ctxt delta over the idle window
#   interrupts_per_s           /proc/stat intr delta over the idle window
#   idle_cpu_percent           CPU percentage in use over the idle window
#   diskstats_reads_completed  /proc/diskstats reads, cumulative since boot
#   diskstats_sectors_read     /proc/diskstats sectors, cumulative since boot
#   diskstats_mib_read         the same reads in MiB
#   pkg_manager                dpkg/apt, rpm/dnf, apk or xbps detected
#   package_count              installed packages counted by that manager
#   pkg_manager_query_ms       how long that read-only count took
#
# Usage: guest-probe.sh [--selftest] [--idle <seconds>]
#   --selftest  measures the machine this script runs on with a short window;
#               it is what tests/test_bench_matrix.py runs offline.
#   --idle N    idle window in seconds (default 10, or BENCH_PROBE_IDLE_SECONDS).
#
# Exit codes: 0 = every metric emitted or explicitly skipped, 1 = /proc is
# unreadable, 2 = bad arguments.
set -eu

usage() {
    cat >&2 <<'USAGE'
Usage: guest-probe.sh [--selftest] [--idle <seconds>]

Print INFO: <metric>=<value> lines for the machine this script runs on, reading
/proc and the script's own clock only. --selftest uses a short idle window so
the probe is exercisable on a development machine without a VM.

Environment: BENCH_PROBE_IDLE_SECONDS (10).
USAGE
}

IDLE_SECONDS=${BENCH_PROBE_IDLE_SECONDS:-10}
SELFTEST=no
while [ $# -gt 0 ]; do
    case "$1" in
        --selftest)
            SELFTEST=yes
            shift
            ;;
        --idle)
            if [ $# -lt 2 ] || ! [[ "$2" =~ ^[0-9]+$ ]] || [ "$2" -lt 1 ]; then
                echo "Invalid idle window: ${2:-}" >&2
                usage
                exit 2
            fi
            IDLE_SECONDS=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 2
            ;;
    esac
done
if [ "$SELFTEST" = yes ] && [ "$IDLE_SECONDS" -gt 3 ]; then
    IDLE_SECONDS=3
fi
if ! command -v sleep >/dev/null 2>&1 || ! command -v awk >/dev/null 2>&1; then
    echo "sleep and awk are required by the benchmark probe" >&2
    exit 2
fi

METRIC_COUNT=0
SKIP_COUNT=0

info() {
    METRIC_COUNT=$((METRIC_COUNT + 1))
    echo "INFO: $1=$2"
}

skip() {
    SKIP_COUNT=$((SKIP_COUNT + 1))
    echo "SKIP: $1 not available on this distro"
}

# Busybox date has no %N, so the clock falls back to whole seconds; both ends of
# the idle window use this same function, so the rate metrics stay correct.
now_ns() {
    local raw
    raw=$(date +%s%N 2>/dev/null || true)
    if [[ "$raw" =~ ^[0-9]{18,}$ ]]; then
        printf '%s\n' "$raw"
    else
        date +%s000000000
    fi
}

# LC_ALL=C on every awk call: the rates must print with a decimal point on a
# distro whose locale uses a comma.
read_stat() {
    local prefix=$1
    LC_ALL=C awk -v prefix="$prefix" '
        $1 == prefix { for (i = 2; i <= NF; i++) sum += $i; printf "%d", sum; exit }
    ' /proc/stat
}

if [ ! -r /proc/uptime ]; then
    echo "ERROR: /proc is not readable; the probe needs a Linux /proc" >&2
    exit 1
fi

info probe_label "$(LC_ALL=C awk '{ printf "%s", $1 }' /proc/version 2>/dev/null)"
info uptime_at_desktop_ready_s "$(LC_ALL=C awk '{ printf "%.1f", $1 }' /proc/uptime)"

# free(1) reports used = total - free - buffers - cached; /proc/meminfo is read
# directly so the probe needs no coreutils beyond awk.
mem_used_mib=$(LC_ALL=C awk '
    /^MemTotal:/ { total = $2 }
    /^MemFree:/ { free = $2 }
    /^Buffers:/ { buffers = $2 }
    /^Cached:/ { cached = $2 }
    END {
        if (total == "" || free == "") { print "unavailable"; exit }
        printf "%.1f", (total - free - buffers - cached) / 1024
    }' /proc/meminfo)
if [ "$mem_used_mib" = unavailable ]; then
    skip mem_used_mib
else
    info mem_used_mib "$mem_used_mib"
fi

# A shell glob over /proc, so no ls, no grep and no locale assumptions.
process_count=0
for entry in /proc/[0-9]*; do
    [ -d "$entry" ] && process_count=$((process_count + 1))
done
if [ -z "$process_count" ] || [ "$process_count" = 0 ]; then
    skip process_count
else
    info process_count "$process_count"
fi

# VmRSS is already in KiB; processes this user may not read drop out rather
# than becoming a zero.
top10_rss_kib=$(grep -h '^VmRSS:' /proc/[0-9]*/status 2>/dev/null |
    LC_ALL=C awk '{ print $2 }' | sort -rn | head -n 10 |
    LC_ALL=C awk '{ sum += $1 } END { printf "%d", sum + 0 }')
if [ -z "$top10_rss_kib" ] || [ "$top10_rss_kib" = 0 ]; then
    skip top10_rss_kib
else
    info top10_rss_kib "$top10_rss_kib"
fi

cpu_line() {
    LC_ALL=C awk '/^cpu / { sub(/^cpu[ \t]+/, ""); print }' /proc/stat
}

stat0_ctxt=$(read_stat ctxt)
stat0_intr=$(read_stat intr)
cpu0=$(cpu_line)
t0=$(now_ns)
sleep "$IDLE_SECONDS"
t1=$(now_ns)
stat1_ctxt=$(read_stat ctxt)
stat1_intr=$(read_stat intr)
cpu1=$(cpu_line)
elapsed=$(LC_ALL=C awk -v t0="$t0" -v t1="$t1" 'BEGIN { printf "%.3f", (t1 - t0) / 1000000000 }')

if [ -z "$stat0_ctxt" ] || [ -z "$stat1_ctxt" ]; then
    skip context_switches_per_s
else
    info context_switches_per_s "$(LC_ALL=C awk -v b="$stat0_ctxt" -v a="$stat1_ctxt" \
        -v e="$elapsed" 'BEGIN { printf "%.1f", (a - b) / e }')"
fi
if [ -z "$stat0_intr" ] || [ -z "$stat1_intr" ]; then
    skip interrupts_per_s
else
    info interrupts_per_s "$(LC_ALL=C awk -v b="$stat0_intr" -v a="$stat1_intr" \
        -v e="$elapsed" 'BEGIN { printf "%.1f", (a - b) / e }')"
fi
if [ -z "$cpu0" ] || [ -z "$cpu1" ]; then
    skip idle_cpu_percent
else
    # Same formula as release-measure.sh: the CPU percentage in use while the
    # machine sits idle, i.e. the total delta minus the idle and idlelow fields.
    info idle_cpu_percent "$(LC_ALL=C awk -v c0="$cpu0" -v c1="$cpu1" '
        BEGIN {
            n = split(c0, a); split(c1, b); total = 0; idle = 0
            for (i = 1; i <= n; i++) {
                total += b[i] - a[i]
                if (i == 4 || (i == 5 && i <= n)) idle += b[i] - a[i]
            }
            if (total < 1) total = 1
            printf "%.2f", 100.0 * (total - idle) / total
        }')"
fi
info idle_window_seconds "$elapsed"

# Cumulative since boot, the way release-measure.sh reads diskstats at
# desktop-ready: whole disks and partitions, no loop devices or mappers.
if [ -r /proc/diskstats ]; then
    info diskstats_reads_completed "$(LC_ALL=C awk '
        $3 !~ /^(loop|mapper|docker|overlay)/ { reads += $4 }
        END { printf "%d", reads + 0 }' /proc/diskstats)"
    info diskstats_sectors_read "$(LC_ALL=C awk '
        $3 !~ /^(loop|mapper|docker|overlay)/ { sectors += $6 }
        END { printf "%d", sectors + 0 }' /proc/diskstats)"
    info diskstats_mib_read "$(LC_ALL=C awk '
        $3 !~ /^(loop|mapper|docker|overlay)/ { sectors += $6 }
        END { printf "%.1f", sectors * 512 / 1048576 }' /proc/diskstats)"
else
    skip diskstats_reads_completed
    skip diskstats_sectors_read
    skip diskstats_mib_read
fi

# The package manager is detected by what already exists, never installed, and
# every command below only lists installed packages.
pkg_manager=
if command -v dpkg-query >/dev/null 2>&1; then
    pkg_manager=dpkg
elif command -v rpm >/dev/null 2>&1; then
    pkg_manager=rpm
elif command -v apk >/dev/null 2>&1; then
    pkg_manager=apk
elif command -v xbps-query >/dev/null 2>&1; then
    pkg_manager=xbps
fi
if [ -z "$pkg_manager" ]; then
    skip pkg_manager
    skip package_count
    skip pkg_manager_query_ms
else
    info pkg_manager "$pkg_manager"
    query0=$(now_ns)
    package_count=0
    # shellcheck disable=SC2016  # ${Package} is expanded by dpkg-query, not here
    case "$pkg_manager" in
        dpkg) package_count=$(dpkg-query -W -f='${Package}\n' 2>/dev/null | wc -l | tr -d '[:space:]') ;;
        rpm) package_count=$(rpm -qa 2>/dev/null | wc -l | tr -d '[:space:]') ;;
        apk) package_count=$(apk info 2>/dev/null | wc -l | tr -d '[:space:]') ;;
        xbps) package_count=$(xbps-query -l 2>/dev/null | wc -l | tr -d '[:space:]') ;;
    esac
    query1=$(now_ns)
    if [ -z "$package_count" ] || [ "$package_count" = 0 ]; then
        skip package_count
        skip pkg_manager_query_ms
    else
        info package_count "$package_count"
        info pkg_manager_query_ms "$(LC_ALL=C awk -v a="$query0" -v b="$query1" \
            'BEGIN { printf "%d", (b - a) / 1000000 }')"
    fi
fi

if [ "$SELFTEST" = yes ]; then
    echo "RESULT: selftest metrics=$METRIC_COUNT skipped=$SKIP_COUNT idle_seconds=$IDLE_SECONDS"
    exit 0
fi
echo "RESULT: probe metrics=$METRIC_COUNT skipped=$SKIP_COUNT"
exit 0
