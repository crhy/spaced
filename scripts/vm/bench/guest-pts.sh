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
#
# Why the sweep used to print NO PTS number (issue #424, task b03):
#   batch-setup was answered with `printf "\n\n\n..."`, i.e. every DEFAULT, and
#   the defaults turn ON "prompt for test identifier", "prompt for test
#   description", "prompt for saved results file-name" and auto-upload. So
#   batch-benchmark printed the system-info block and then hung waiting for a
#   test name that nobody typed. The run log ended right after the spectre/vmscape
#   lines and the host saw `captured=0 rc=124` at the cap. The fix is to answer
#   every batch option EXPLICITLY (off for the prompts, on for saving, off for
#   upload/viewer) and to hand the result name/identifier/description through
#   TEST_RESULTS_NAME/TEST_RESULTS_IDENTIFIER/TEST_RESULTS_DESCRIPTION, then run
#   with `batch-run`, stdin from /dev/null, under a per-test timeout that marks
#   which step it was in.

set -u

TESTS=${PTS_TESTS:-"pts/compress-zstd pts/sqlite-speedtest pts/c-ray"}
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

post_partial() {
    # The host's own cap can end the VM at any moment, so every finished test
    # is posted as it lands rather than only in one final batch.
    leaf=$1
    [ -f "$WORK/$leaf" ] || return 0
    url="http://$HOST:$PORT/$LABEL/$leaf"
    if command -v curl >/dev/null 2>&1; then
        curl -s -T "$WORK/$leaf" "$url" >/dev/null 2>&1 && return 0
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 -c '
import sys, urllib.request
name, leaf, host, port, label = sys.argv[1:6]
data = open(name, "rb").read()
request = urllib.request.Request("http://%s:%s/%s/%s"
                                 % (host, port, label, leaf), data=data)
urllib.request.urlopen(request, timeout=60).read()
' "$WORK/$leaf" "$leaf" "$HOST" "$PORT" "$LABEL" >/dev/null 2>&1 && return 0
    fi
    wget --post-file="$WORK/$leaf" -q -O /dev/null "$url" >/dev/null 2>&1
}

# What PHP/devel each family needs on top of the distro PTS package, so the
# tests build offline. Every family is recorded in install.log.
install_pts() {
    if command -v phoronix-test-suite >/dev/null 2>&1; then
        note "install family=$DISTRO: already installed"
        return 0
    fi
    case "$DISTRO" in
        debian|ubuntu|mint|zorin|mx|spaced)
            note "install family=apt($DISTRO): apt-get update && apt-get install phoronix-test-suite php-cli php-xml php-zip unzip build-essential"
            $SUDO apt-get update >> "$PTSDIR/install.log" 2>&1
            # env, not a bare assignment prefix: once $SUDO expands, dash stops
            # reading an assignment as one and would exec the assignment itself.
            $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y \
                phoronix-test-suite >> "$PTSDIR/install.log" 2>&1 ;;
        fedora)
            note "install family=dnf($DISTRO): dnf install phoronix-test-suite (pulls php) + @development-tools php-cli php-xml php-zip unzip"
            $SUDO dnf install -y phoronix-test-suite \
                >> "$PTSDIR/install.log" 2>&1 ;;
        void)
            note "install family=xbps($DISTRO): xbps-install phoronix-test-suite (pulls php8) + base-devel"
            $SUDO xbps-install -Sy phoronix-test-suite \
                >> "$PTSDIR/install.log" 2>&1 ;;
        cachyos|arch)
            note "install family=pacman($DISTRO): pacman -S phoronix-test-suite (pulls php) + base-devel"
            $SUDO pacman -Sy --noconfirm phoronix-test-suite \
                >> "$PTSDIR/install.log" 2>&1 ;;
        *)
            note "install family=none($DISTRO): no known package manager"
            return 1 ;;
    esac
    if command -v phoronix-test-suite >/dev/null 2>&1; then
        note "install family=$DISTRO: distro package installed"
        return 0
    fi
    # Debian and Devuan no longer package PTS, so fall back to the official
    # upstream release (PHP is what the suite itself runs on). Every other
    # distro's package manager is expected to carry it.
    case "$DISTRO" in
        debian|ubuntu|mint|zorin|mx|spaced) ;;
        *) note "install family=$DISTRO: distro package not found"; return 1 ;;
    esac
    note "install family=apt($DISTRO): no distro package; upstream $PTS_VERSION deb + php-cli php-xml php-zip unzip build-essential"
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
# any test runs: an unconfigured batch mode makes batch-run refuse to print any
# result line, and answering batch-setup with defaults (the old bug) turns the
# identifier/description/save-name prompts ON, which hangs every run right
# after the system-info block. Every option is now named explicitly.
configure_pts() {
    export PTS_RESULT_DIRECTORY=$PTSDIR/results
    mkdir -p "$HOME/.phoronix-test-suite" "$PTSDIR/results" 2>/dev/null
    # The graph options below are not enough: PTS loads load_dynamic_result_viewer
    # at start-up, which forks `php -S localhost:PORT` and waits for a browser to
    # poll it. In a headless live session with PHP 8.4 that server never answers,
    # so every batch run hangs before the first test starts. PTS globs
    # *.php in its module directory, so renaming the file keeps it unloaded.
    $SUDO mv -f \
        /usr/share/phoronix-test-suite/pts-core/modules/load_dynamic_result_viewer.php \
        /usr/share/phoronix-test-suite/pts-core/modules/load_dynamic_result_viewer.php.disabled \
        >> "$PTSDIR/batch-setup.log" 2>&1 || true
    # Answer the one-time first-run questions so PTS never prompts for a
    # display name / update opt-in at the start of a batch run.
    printf 'True\n' | timeout 60 phoronix-test-suite force-configuration \
        > /dev/null 2>&1
    # THE b03 FIX. batch-setup writes the batch options to
    # user-config.xml under Options/BatchMode/* and sets Configured=TRUE, which
    # is the flag batch-run/batch-benchmark require ("The batch mode must first
    # be configured"). The old bug was `printf "\n\n\n..." | batch-setup`: an
    # empty line accepts the DEFAULT, and the defaults are SaveResults=TRUE,
    # OpenBrowser=FALSE, UploadResults=TRUE, and Prompt{ForTestIdentifier,
    # ForTestDescription,SaveName}=TRUE, RunAllTestCombinations=TRUE. Answered
    # explicitly, in the order batch_setup.php prompts:
    #   SaveResults y | OpenBrowser n | UploadResults n |
    #   PromptForTestIdentifier n | PromptForTestDescription n | PromptSaveName n |
    #   RunAllTestCombinations n
    # (Configured is set to TRUE by batch-setup itself.) With the prompts off,
    # batch-run uses TEST_RESULTS_NAME/IDENTIFIER/DESCRIPTION and never waits on
    # a test name after the system-info block.
    note "configure: answering batch-setup explicitly (save=y, upload/viewer/prompts=n)"
    printf 'y\nn\nn\nn\nn\nn\nn\n' | timeout 120 phoronix-test-suite batch-setup \
        > "$PTSDIR/batch-setup.log" 2>&1
    # Belt and suspenders: the graph options are top-level, not under BatchMode,
    # so the `option` command can still reach them; a headless run must not try
    # to open a browser or a live graph.
    for opt in "BatchRunDisplayDynamicGraph FALSE" "BatchRunDisplayGraph FALSE"; do
        name=${opt% *}
        value=${opt#* }
        timeout 60 phoronix-test-suite option "$name" "$value" \
            >> "$PTSDIR/batch-setup.log" 2>&1
    done
    # Prove the config actually took, so an option PTS refused to set is visible
    # in the log rather than hanging the run later. (10.8.4 has no
    # user-config-get subcommand; read the file it wrote instead.)
    cat "$HOME/.phoronix-test-suite/user-config.xml" > "$PTSDIR/user-config.log" 2>&1
    note "configure: user-config.xml captured to user-config.log"
}

# The result name/identifier/description PTS would otherwise prompt for.
# batch-run with these set and the Prompt* options FALSE never waits on stdin.
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
    note "STEP=install test=$test budget=${budget}s"
    timeout "$budget" phoronix-test-suite batch-install \
        "$test" < /dev/null > "$PTSDIR/install-$short.log" 2>&1
    rc=$?
    note "STEP=install-done test=$test rc=$rc"
    budget=$(remaining)
    if [ "$budget" -lt 30 ]; then
        printf '%s\t%s\t\t\t\tcap-reached-before-run\n' \
            "$LABEL" "$test" >> "$WORK/pts.tsv"
        return
    fi
    # A per-test result name keeps batch-run from asking for one; PTS writes the
    # composite.xml under this name so the value can be re-checked line by line.
    name="b03-$short"
    note "STEP=run test=$test budget=${budget}s"
    TEST_RESULTS_NAME="$name" TEST_RESULTS_IDENTIFIER="$name" \
    TEST_RESULTS_DESCRIPTION="$test on $DISTRO ($LABEL)" \
        timeout "$budget" phoronix-test-suite batch-run \
        "$test" < /dev/null > "$log" 2>&1
    rc=$?
    note "STEP=run-done test=$test rc=$rc"
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
    post_partial pts-status.txt
    configure_pts
    for test in $TESTS; do
        [ "$(remaining)" -lt 30 ] && break
        run_one "$test"
        # Whatever finished is visible to the host even if the next test is
        # still running when the host's cap ends and the VM is destroyed.
        post_partial pts.tsv
        post_partial pts-status.txt
    done
    # PTS's own files: result XMLs (composite.xml included) plus the raw logs,
    # so the numbers can be re-checked line by line later.
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
