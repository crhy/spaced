#!/bin/sh
# Phoronix Test Suite inside a benchmark guest (issue #424).
#
# #424 asks for a third-party suite so the numbers cannot be called fudged.
# This script installs the distro's own phoronix-test-suite package (the
# official upstream one; the tarball needs PHP and is never attempted blindly),
# runs a short, network-light, CPU/disk set that exists for every distro, and
# leaves two artifacts for the host:
#
#   $WORK/pts.tsv          one row per test: label test metric value unit status
#   $WORK/pts-results.tar  PTS's own result files plus every raw run log
#
# Env in: LABEL DISTRO SUDO CAP_SECONDS PTS_TESTS WORK HOST PORT
# Nothing is skipped silently: every install or run failure is a status= value.

set -u

TESTS=${PTS_TESTS:-"pts/compress-zstd pts/sqlite-speedtest pts/openssl"}
PTS_VERSION=${PTS_VERSION:-10.8.4}
START=$(date +%s)
PTSDIR=$WORK/pts

used() {
    echo $(( $(date +%s) - START ))
}

remaining() {
    left=$(( CAP_SECONDS - $(used) ))
    [ "$left" -lt 0 ] && left=0
    echo "$left"
}

note() {
    printf '%s: %s\n' "$(date -u +%T)" "$*" >> "$PTSDIR/install.log"
}

install_pts() {
    if command -v phoronix-test-suite >/dev/null 2>&1; then
        note "already installed"
        return 0
    fi
    case "$DISTRO" in
        debian|ubuntu|mint|zorin|mx|spaced)
            $SUDO apt-get update >> "$PTSDIR/install.log" 2>&1
            # env, not a bare assignment prefix: once $SUDO expands, dash stops
            # reading an assignment as one and would exec the assignment itself.
            $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y \
                phoronix-test-suite >> "$PTSDIR/install.log" 2>&1 ;;
        fedora)
            $SUDO dnf install -y phoronix-test-suite \
                >> "$PTSDIR/install.log" 2>&1 ;;
        void)
            $SUDO xbps-install -Sy phoronix-test-suite \
                >> "$PTSDIR/install.log" 2>&1 ;;
        cachyos|arch)
            $SUDO pacman -Sy --noconfirm phoronix-test-suite \
                >> "$PTSDIR/install.log" 2>&1 ;;
        *)
            note "no known package manager for $DISTRO"
            return 1 ;;
    esac
    if command -v phoronix-test-suite >/dev/null 2>&1; then
        note "distro package"
        return 0
    fi
    # Debian and Devuan no longer package PTS, so fall back to the official
    # upstream release (PHP is what the suite itself runs on). Every other
    # distro's package manager is expected to carry it.
    case "$DISTRO" in
        debian|ubuntu|mint|zorin|mx|spaced) ;;
        *) return 1 ;;
    esac
    note "no distro package; upstream $PTS_VERSION deb"
    # php-cli runs PTS, php-zip/unzip extract the test archives (PTS 10.8.4
    # cannot read its own .zip downloads without them), build-essential and the
    # -dev headers build the tests themselves.
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y php-cli \
        php-xml php-zip unzip build-essential pkg-config zlib1g-dev \
        libssl-dev libsqlite3-dev >> "$PTSDIR/install.log" 2>&1
    curl -sSL -o "$PTSDIR/pts.deb" \
        "https://github.com/phoronix-test-suite/phoronix-test-suite/releases/download/v$PTS_VERSION/phoronix-test-suite_${PTS_VERSION}_all.deb" \
        >> "$PTSDIR/install.log" 2>&1
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y \
        "$PTSDIR/pts.deb" >> "$PTSDIR/install.log" 2>&1
    # PTS 10.8.4 (the last release, 2022) multiplies the DIMM count by a memory
    # size string that is not numeric on QEMU virtual memory, and PHP 8.4 turns
    # that into a fatal TypeError that kills every test run. A numeric guard on
    # the same condition is the smallest fix; the value it skips is only used
    # to guess how many sticks a machine has, never a benchmark result.
    $SUDO sed -i "s/if((\$mem_count \* \$t)/if(\$t > 0 \&\& (\$mem_count * \$t)/" \
        /usr/share/phoronix-test-suite/pts-core/objects/phodevi/components/phodevi_memory.php \
        >> "$PTSDIR/install.log" 2>&1
    command -v phoronix-test-suite >/dev/null 2>&1
}

# PTS answers its one-time questions here so batch mode is configured before
# any test runs: an unconfigured batch mode makes batch-benchmark refuse to
# print any result line.
configure_pts() {
    export PTS_RESULT_DIRECTORY=$PTSDIR/results
    $SUDO mkdir -p "$PTSDIR/results" 2>/dev/null
    mkdir -p "$HOME/.phoronix-test-suite" 2>/dev/null
    printf '\n\n\n\n\n\n\n\n' | timeout 120 phoronix-test-suite batch-setup \
        > "$PTSDIR/batch-setup.log" 2>&1
    printf 'True\n' | timeout 60 phoronix-test-suite force-configuration \
        > /dev/null 2>&1
    yes 2>/dev/null | timeout 60 phoronix-test-suite system-info \
        > "$PTSDIR/system-info.log" 2>&1
}

run_one() {
    test=$1
    short=$(printf '%s' "$test" | tr -c 'A-Za-z0-9._-' '_')
    log=$PTSDIR/run-$short.log
    budget=$(remaining)
    if [ "$budget" -lt 30 ]; then
        printf '%s\t%s\t\t\t\tcap-reached-before-install\n' \
            "$LABEL" "$test" >> "$WORK/pts.tsv"
        return
    fi
    # </dev/null, not `yes |`: an installer reading its stdin from a yes-pipe
    # dies with "cat: write error: Broken pipe" once PTS stops asking.
    timeout "$budget" phoronix-test-suite batch-install \
        "$test" < /dev/null > "$PTSDIR/install-$short.log" 2>&1
    budget=$(remaining)
    if [ "$budget" -lt 30 ]; then
        printf '%s\t%s\t\t\t\tcap-reached-before-run\n' \
            "$LABEL" "$test" >> "$WORK/pts.tsv"
        return
    fi
    timeout "$budget" phoronix-test-suite batch-benchmark \
        "$test" < /dev/null > "$log" 2>&1
    rc=$?
    if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ] && ! grep -q 'Test Total Time' "$log"; then
        printf '%s\t%s\t\t\t\trun-failed-rc-%s\n' "$LABEL" "$test" "$rc" \
            >> "$WORK/pts.tsv"
        return
    fi
    captured=0
    grep -E '^Test (Total Time|Result|Raw Values)' "$log" | while IFS= read -r line; do
        metric=$(printf '%s' "$line" | sed -n 's/^Test \([A-Za-z ]*\):.*/\1/p' \
            | tr ' ' '-' | tr 'A-Z' 'a-z')
        value=$(printf '%s' "$line" | sed -n 's/^.*: *//p' \
            | sed -n 's/^\([0-9][0-9.]*\).*/\1/p')
        unit=$(printf '%s' "$line" | sed -n 's/^.*: *[0-9][0-9.]* *\(.*\)$/\1/p' \
            | tr -d ' ')
        printf '%s\t%s\t%s\t%s\t%s\tok\n' "$LABEL" "$test" "$metric" \
            "$value" "$unit" >> "$WORK/pts.tsv"
    done
    if ! grep -q 'Test Total Time' "$log"; then
        printf '%s\t%s\t\t\t\tno-result-line\n' "$LABEL" "$test" >> "$WORK/pts.tsv"
    else
        captured=1
    fi
    note "$test captured=$captured rc=$rc"
}

mkdir -p "$PTSDIR"
: > "$WORK/pts.tsv"
printf 'label\ttest\tmetric\tvalue\tunit\tstatus\n' >> "$WORK/pts.tsv"

if install_pts; then
    printf 'pts_install=ok\n' >> "$WORK/pts-status.txt"
    configure_pts
    for test in $TESTS; do
        [ "$(remaining)" -lt 30 ] && break
        run_one "$test"
    done
    # PTS's own files: result XMLs plus the raw logs, so the numbers can be
    # re-checked line by line later.
    find "$HOME/.phoronix-test-suite" -type f \
        \( -name '*.xml' -o -name '*result*' \) 2>/dev/null |
        while read -r found; do
            cp "$found" "$PTSDIR/" 2>/dev/null
        done
    tar -C "$PTSDIR" -cf "$WORK/pts-results.tar" . 2>/dev/null
    printf 'pts_tests=%s\n' "$(printf '%s' "$TESTS" | wc -w)" \
        >> "$WORK/pts-status.txt"
else
    printf 'pts_install=failed\n' >> "$WORK/pts-status.txt"
    note "phoronix-test-suite not installable on $DISTRO"
fi
printf 'pts_seconds=%s\n' "$(used)" >> "$WORK/pts-status.txt"
cat "$PTSDIR/install.log" >> "$WORK/pts-status.txt" 2>/dev/null
exit 0
