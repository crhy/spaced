#!/bin/bash
# Exercise source/key rollback and bootstrap decisions with fixture commands
# in a rootless namespace. No host configuration or package state is writable.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
mkdir -p "$WORK/bin"
cat > "$WORK/bin/apt-get" <<'MOCK'
#!/bin/bash
printf 'apt-get %s\n' "$*" >> /commands.log
if [[ " $* " == *' update '* && ${FAIL_UPDATE:-0} == 1 ]]; then exit 42; fi
if [[ " $* " == *' --simulate '* ]]; then
    [[ ${UNSAFE_PLAN:-0} != 1 ]] || echo 'Inst systemd-sysv (260)'
elif [[ " $* " == *' install '* && ${FAIL_INSTALL:-0} == 1 ]]; then
    exit 42
fi
MOCK
cat > "$WORK/bin/apt-cache" <<'MOCK'
#!/bin/sh
printf 'spaced-meta:\n  Installed: (none)\n  Candidate: 9.26\n'
MOCK
cat > "$WORK/bin/dpkg" <<'MOCK'
#!/bin/sh
printf 'dpkg %s\n' "$*" >> /commands.log
if [ "$1" = --compare-versions ]; then exec /usr/bin/dpkg "$@"; fi
MOCK
chmod +x "$WORK/bin/"*
for scenario in success wrong-key failed-refresh unsafe-plan failed-install; do
    fixture="$WORK/$scenario"
    mkdir -p "$fixture"/{etc/apt/sources.list.d,usr/share/keyrings,usr/lib/spaced-linux,run/lock}
    ln -s usr/bin "$fixture/bin"
    ln -s usr/lib "$fixture/lib"
    printf 'ID=spaced\nVERSION_ID="7.26.3"\n' > "$fixture/etc/os-release"
    printf 'deb [trusted=yes] http://legacy.invalid spaced main\n' > "$fixture/etc/apt/sources.list.d/spaced-apt.list"
    printf 'original key\n' > "$fixture/usr/share/keyrings/spaced-archive-keyring.gpg"
    printf 'tampered key\n' > "$fixture/bad-key.gpg"
    cat > "$fixture/usr/lib/spaced-linux/spaced-update-helper" <<'MOCK'
#!/bin/sh
printf 'helper %s\n' "$*" >> /commands.log
MOCK
    chmod +x "$fixture/usr/lib/spaced-linux/spaced-update-helper"
    extra=()
    case "$scenario" in
        wrong-key) extra=(--keyring /bad-key.gpg) ;;
        failed-refresh) extra_env=(--setenv FAIL_UPDATE 1) ;;
        unsafe-plan) extra_env=(--setenv UNSAFE_PLAN 1) ;;
        failed-install) extra_env=(--setenv FAIL_INSTALL 1) ;;
    esac
    status=0
    bwrap --die-with-parent --unshare-all --uid 0 --gid 0 \
        --bind "$fixture" / --ro-bind "$ROOT" /project --ro-bind "$WORK/bin" /test-bin \
        --ro-bind /usr/bin /usr/bin --ro-bind /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu \
        --ro-bind /lib64 /lib64 --proc /proc --dev /dev --tmpfs /tmp \
        --setenv PATH /test-bin:/usr/bin:/bin --unsetenv SUDO_UID --unsetenv PKEXEC_UID \
        "${extra_env[@]}" /bin/bash /project/scripts/spaced-upgrade-testing.sh --apply \
        --repository http://test.invalid "${extra[@]}" > "$WORK/$scenario.log" 2>&1 || status=$?
    extra_env=()
    case "$scenario" in
        success)
            [[ $status == 0 ]] || { cat "$WORK/$scenario.log" >&2; exit 1; }
            grep -q 'install spaced-meta' "$fixture/commands.log"
            grep -qx 'helper all' "$fixture/commands.log"
            grep -q 'http://test.invalid spaced-testing main' "$fixture/etc/apt/sources.list.d/spaced-apt.list"
            cmp "$fixture/usr/share/keyrings/spaced-archive-keyring.gpg" "$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg"
            ;;
        failed-install)
            [[ $status == 42 ]]
            grep -q 'http://test.invalid spaced-testing main' "$fixture/etc/apt/sources.list.d/spaced-apt.list"
            ! grep -q 'helper all' "$fixture/commands.log"
            ;;
        *)
            [[ $status != 0 ]]
            grep -qx 'deb \[trusted=yes\] http://legacy.invalid spaced main' "$fixture/etc/apt/sources.list.d/spaced-apt.list"
            grep -qx 'original key' "$fixture/usr/share/keyrings/spaced-archive-keyring.gpg"
            if [[ -f "$fixture/commands.log" ]]; then ! grep -q 'helper all' "$fixture/commands.log"; fi
            ;;
    esac
    echo "PASS: testing bootstrap $scenario"
done
