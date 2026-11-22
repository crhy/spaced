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
#   settle_time_s              first guest uptime after desktop-ready at which
#                              CPU in use stays < 1% for 10 s in a row (poll
#                              /proc/stat every 1 s); empty if it never settles
#                              before the idle window
#   idle_sample_start_uptime_s guest uptime the idle window started at
#   idle_status                ok (the desktop was up by the fixed start point)
#                              or late (it came later, idle not measured)
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
# The idle window starts at a FIXED guest uptime (BENCH_IDLE_START_UPTIME,
# default 300), equal to the runner's 300 s desktop timeout, so every OS that
# booted is on its desktop by then and the same uptime is sampled for every
# distro. A distro whose desktop comes later than that point is marked
# idle_status=late instead of being measured at a different uptime (b02 found
# Spaced at 29.5% CPU at 11 s but 0.05% at 180 s, so sampling each OS at its own
# ready time compared boot storms, not idle machines).
#
# Usage: guest-probe.sh [--selftest] [--idle <seconds>]
#   --selftest  measures the machine this script runs on with a short window;
#               it is what tests/test_bench_matrix.py runs offline.
#   --idle N    idle window in seconds (default 60, or BENCH_PROBE_IDLE_SECONDS).
#
# Environment: BENCH_PROBE_IDLE_SECONDS (60), BENCH_IDLE_START_UPTIME (300).
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

Environment: BENCH_PROBE_IDLE_SECONDS (60), BENCH_IDLE_START_UPTIME (300).
USAGE
}

IDLE_SECONDS=${BENCH_PROBE_IDLE_SECONDS:-60}
IDLE_START_UPTIME=${BENCH_IDLE_START_UPTIME:-300}
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

# CPU percentage in use between two /proc/stat cpu lines (total minus idle and
# iowait), the same formula as release-measure.sh, reused for the settle probe.
cpu_in_use() {
    LC_ALL=C awk -v c0="$1" -v c1="$2" '
        BEGIN {
            n = split(c0, a); split(c1, b); total = 0; idle = 0
            for (i = 1; i <= n; i++) {
                total += b[i] - a[i]
                if (i == 4 || (i == 5 && i <= n)) idle += b[i] - a[i]
            }
            if (total < 1) total = 1
            printf "%.2f", 100.0 * (total - idle) / total
        }'
}

# A guest's uptime as a float, so the idle window starts at the same fixed
# uptime for every operating system.
uptime_f() {
    LC_ALL=C awk '{ printf "%.1f", $1 }' /proc/uptime
}

uptime0=$(uptime_f)

# Where the idle window starts. --selftest measures this machine now; a real
# guest waits until the fixed point so every OS is sampled at the same uptime.
late=0
if [ "$SELFTEST" = yes ]; then
    target_start=$uptime0
    idle_status=ok
elif LC_ALL=C awk -v u="$uptime0" -v t="$IDLE_START_UPTIME" 'BEGIN { exit !(u > t) }'; then
    # The desktop came later than the fixed point: mark it, do not measure at a
    # different uptime and pretend it matched the other operating systems.
    late=1
    idle_status=late
    target_start=$uptime0
else
    target_start=$IDLE_START_UPTIME
    idle_status=ok
fi
target_end=$(LC_ALL=C awk -v s="$target_start" -v w="$IDLE_SECONDS" 'BEGIN { printf "%.1f", s + w }')

# From desktop-ready, poll /proc/stat every 1 s to find settle_time_s (the first
# uptime at which CPU in use stays < 1% for 10 s in a row). The same poll waits
# out the fixed start point, so the idle window sample is taken at target_start
# and the settle probe never races a separate clock. A whole `sleep 1` keeps the
# cadence busybox-safe; the window opens within ~1 s of the fixed point.
settle=''
streak=0
first_of_streak=''
prev_cpu=''
prev_uptime=''
win_start=''
win0_ctxt=''
win0_intr=''
win0_cpu=''
win0_t=''
win_end=''
win1_ctxt=''
win1_intr=''
win1_cpu=''
win1_t=''
poll_i=0
poll_max=$(( IDLE_START_UPTIME + IDLE_SECONDS + 120 ))
while : ; do
    u=$(uptime_f)
    ctxt=$(read_stat ctxt)
    intr=$(read_stat intr)
    cpu=$(cpu_line)
    if [ -n "$prev_cpu" ]; then
        pct=$(cpu_in_use "$prev_cpu" "$cpu")
        if LC_ALL=C awk -v p="$pct" 'BEGIN { exit !(p < 1) }'; then
            streak=$((streak + 1))
            [ "$streak" -eq 1 ] && first_of_streak=$prev_uptime
            if [ -z "$settle" ] && [ "$streak" -ge 10 ]; then
                settle=$first_of_streak
            fi
        else
            streak=0
        fi
    fi
    if [ -z "$win_start" ] && LC_ALL=C awk -v u="$u" -v t="$target_start" 'BEGIN { exit !(u >= t) }'; then
        win_start=$u
        win0_ctxt=$ctxt
        win0_intr=$intr
        win0_cpu=$cpu
        win0_t=$(now_ns)
    fi
    prev_cpu=$cpu
    prev_uptime=$u
    if [ -n "$win_start" ] && LC_ALL=C awk -v u="$u" -v t="$target_end" 'BEGIN { exit !(u >= t) }'; then
        win_end=$u
        win1_ctxt=$ctxt
        win1_intr=$intr
        win1_cpu=$cpu
        win1_t=$(now_ns)
        break
    fi
    poll_i=$((poll_i + 1))
    [ "$poll_i" -ge "$poll_max" ] && break
    sleep 1
done

# The three fixed-idle columns always exist, even when the machine is late or
# never settles, so one row lands in every TSV column.
info idle_sample_start_uptime_s "${win_start:-$uptime0}"
info idle_status "$idle_status"
info settle_time_s "$settle"

if [ "$late" = 1 ] || [ -z "$win_start" ] || [ -z "$win_end" ]; then
    skip context_switches_per_s
    skip interrupts_per_s
    skip idle_cpu_percent
    skip idle_window_seconds
else
    elapsed=$(LC_ALL=C awk -v t0="$win0_t" -v t1="$win1_t" \
        'BEGIN { printf "%.3f", (t1 - t0) / 1000000000 }')
    if [ -z "$win0_ctxt" ] || [ -z "$win1_ctxt" ]; then
        skip context_switches_per_s
    else
        info context_switches_per_s "$(LC_ALL=C awk -v b="$win0_ctxt" -v a="$win1_ctxt" \
            -v e="$elapsed" 'BEGIN { printf "%.1f", (a - b) / e }')"
    fi
    if [ -z "$win0_intr" ] || [ -z "$win1_intr" ]; then
        skip interrupts_per_s
    else
        info interrupts_per_s "$(LC_ALL=C awk -v b="$win0_intr" -v a="$win1_intr" \
            -v e="$elapsed" 'BEGIN { printf "%.1f", (a - b) / e }')"
    fi
    if [ -z "$win0_cpu" ] || [ -z "$win1_cpu" ]; then
        skip idle_cpu_percent
    else
        # Same formula as release-measure.sh: the CPU percentage in use while the
        # machine sits idle, i.e. the total delta minus the idle and idlelow fields.
        info idle_cpu_percent "$(LC_ALL=C awk -v c0="$win0_cpu" -v c1="$win1_cpu" '
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
fi

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
