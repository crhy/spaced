#!/bin/sh
# Guest-side half of the benchmark bootstrap (issue #424).
#
# The runner types ONE short command into the live desktop's terminal; that
# command pipes this file through sh. Everything it needs arrives from the
# host's http server (10.0.2.2 in QEMU's user-mode network), and every result
# goes back over the same channel, so no distro has to offer an SSH server,
# open a port, or be touched on disk.
#
# The generated per-OS bootstrap (build/bench/<label>/b.sh) exports LABEL,
# DISTRO, HOST, PORT, IDLE_SECONDS, CAP_SECONDS, SUDO and FETCH before piping
# this script. It is plain POSIX sh because the live desktop's terminal runs
# whatever shell the distro ships.
#
# Nothing here is installed, and nothing is measured on the host: the probe
# reads /proc, and the setup script installs benchmark tools only when the
# distro's own package manager is asked to.

SHELL_BIN=${SHELL_BIN:-sh}
BEACON=/tmp/bench-beacon.txt
WORK=/tmp/bench-work
mkdir -p "$WORK"

post() {
    # post <leaf> <file>: push a file back to the host server. curl first,
    # then python3, then GNU wget: every distro tested has at least one.
    leaf=$1
    file=$2
    [ -f "$file" ] || return 1
    url="http://$HOST:$PORT/$leaf"
    if command -v curl >/dev/null 2>&1; then
        curl -s -T "$file" "$url" >/dev/null && return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import sys, urllib.request
name, leaf = sys.argv[1], sys.argv[2]
data = open(name, "rb").read()
request = urllib.request.Request(
    "http://%s:%s/%s" % (sys.argv[3], sys.argv[4], leaf), data=data)
urllib.request.urlopen(request, timeout=120).read()
' "$file" "$leaf" "$HOST" "$PORT" && return 0
    fi
    wget --post-file="$file" -q -O /dev/null "http://$HOST:$PORT/$leaf" \
        && return 0
    return 1
}

fetch() {
    # fetch <remote-leaf> <local-file>: wget and curl are the live desktop's
    # own; python3 covers a distro that ships neither in the live session.
    leaf=$1
    out=$2
    url="http://$HOST:$PORT/$leaf"
    case "$FETCH_TOOL" in
        curl) curl -sf "$url" -o "$out" 2>/dev/null ;;
        python3)
            python3 -c '
import sys, urllib.request
sys.stdout.buffer.write(urllib.request.urlopen(sys.argv[1]).read())
' "$url" > "$out" 2>/dev/null ;;
        *) wget -q -O "$out" "$url" 2>/dev/null ;;
    esac
    [ -s "$out" ]
}

status() {
    printf '%s\n' "$*" >> "$WORK/status.txt"
}

# 1. Beacon: the runner counts this as "the live desktop is reachable and the
#    terminal accepted our command", which is also its boot-to-desktop clock.
{
    printf 'label=%s\n' "$LABEL"
    printf 'distro=%s\n' "$DISTRO"
    printf 'user=%s\n' "$(id -un 2>/dev/null)"
    printf 'kernel=%s\n' "$(uname -r 2>/dev/null)"
    printf 'os=%s\n' "$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release 2>/dev/null | tr -d '"')"
    printf 'uptime=%s\n' "$(cut -d' ' -f1 /proc/uptime 2>/dev/null)"
    printf 'time=%s\n' "$(date -u +%FT%TZ 2>/dev/null)"
} > "$BEACON"
post "$LABEL/beacon" "$BEACON" || status "beacon failed"

# 2. The f093 probe: the same metrics release-measure.sh reports.
if fetch guest-probe.sh "$WORK/guest-probe.sh"; then
    if command -v bash >/dev/null 2>&1; then
        bash "$WORK/guest-probe.sh" --idle "${IDLE_SECONDS:-20}" \
            > "$WORK/probe.txt" 2>&1
    else
        printf 'SKIP: bash is not installed, the probe needs it\n' \
            > "$WORK/probe.txt"
    fi
    post "$LABEL/probe.txt" "$WORK/probe.txt" || status "probe upload failed"
else
    status "probe fetch failed"
fi

# 3. Phoronix Test Suite: the third-party numbers #424 asked for, run with the
#    distro's own package manager and capped, so nobody can call them fudged.
if fetch guest-pts.sh "$WORK/guest-pts.sh"; then
    LABEL="$LABEL" DISTRO="$DISTRO" SUDO="$SUDO" CAP_SECONDS="$CAP_SECONDS" \
    PTS_TESTS="$PTS_TESTS" HOST="$HOST" PORT="$PORT" WORK="$WORK" \
        "$SHELL_BIN" "$WORK/guest-pts.sh" >> "$WORK/pts-status.txt" 2>&1
    post "$LABEL/pts-status.txt" "$WORK/pts-status.txt" || true
    post "$LABEL/pts-status" "$WORK/pts-status.txt" || true
    if [ -f "$WORK/pts-results.tar" ]; then
        post "$LABEL/pts-results.tar" "$WORK/pts-results.tar" || true
    fi
    if [ -f "$WORK/pts.tsv" ]; then
        post "$LABEL/pts.tsv" "$WORK/pts.tsv" || true
    fi
else
    status "pts fetch failed"
fi

# 4. Done marker: the runner stops waiting when this lands.
status "bootstrap finished"
post "$LABEL/done" "$WORK/status.txt" || true
