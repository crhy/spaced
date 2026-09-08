#!/bin/bash
# Explicit opt-in for existing Spaced systems, including versions without
# spaced-meta or an archive key. Run from a verified release/9.26 checkout.
set -Eeuo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
KEY_SOURCE="$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg"
KEY_SHA256=2a0635bdf3d775eeb5c477b50ab5b592c28b207a957e8573a3fd97c612adbdb5
REPOSITORY=https://crhy.github.io/spaced-apt
APPLY=0
usage() {
    echo 'Usage: sudo bash scripts/spaced-upgrade-testing.sh --apply [--repository URL] [--keyring FILE]'
    echo 'Opts this Spaced installation into the signed spaced-testing suite and upgrades it.'
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        --repository) REPOSITORY=${2:?Missing repository URL}; shift 2 ;;
        --keyring) KEY_SOURCE=${2:?Missing public key file}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
[[ "$APPLY" == 1 ]] || { usage; exit 2; }
[[ "$EUID" == 0 ]] || { echo 'Run this explicit testing upgrade with sudo.' >&2; exit 1; }
grep -Eq '^ID="?spaced"?$' /etc/os-release || {
    echo 'This entrypoint is for an existing Spaced Linux installation.' >&2; exit 1;
}
[[ "$REPOSITORY" =~ ^https?://[^[:space:]]+$ ]] || {
    echo 'Repository must be an HTTP(S) URL without whitespace.' >&2; exit 2;
}
[[ -f "$KEY_SOURCE" ]] || { echo "Missing shipped archive key: $KEY_SOURCE" >&2; exit 1; }
printf '%s  %s\n' "$KEY_SHA256" "$KEY_SOURCE" | sha256sum --check --status || {
    echo 'Archive key differs from the key pinned by this testing entrypoint.' >&2; exit 1;
}
exec 9>/run/lock/spaced-update.lock
flock -n 9 || { echo 'Another Spaced update is running; retry after it finishes.' >&2; exit 75; }

WORK=$(mktemp -d)
KEEP_SOURCE=0
SOURCE=/etc/apt/sources.list.d/spaced-apt.list
KEY=/usr/share/keyrings/spaced-archive-keyring.gpg
for name in source key; do
    if [[ $name == source ]]; then file=$SOURCE; else file=$KEY; fi
    if [[ -e $file || -L $file ]]; then cp -a "$file" "$WORK/$name.original"; fi
done
cleanup() {
    local status=$?
    if [[ "$KEEP_SOURCE" == 0 ]]; then
        for name in source key; do
            if [[ $name == source ]]; then file=$SOURCE; else file=$KEY; fi
            rm -f "$file"
            if [[ -e "$WORK/$name.original" || -L "$WORK/$name.original" ]]; then
                cp -a "$WORK/$name.original" "$file"
            fi
        done
    fi
    rm -rf -- "$WORK"
    exit "$status"
}
trap cleanup EXIT
# Copy before installing so --keyring can refer to the installed key itself.
cp "$KEY_SOURCE" "$WORK/archive-key.gpg"
install -Dm0644 "$WORK/archive-key.gpg" "$KEY"
printf 'deb [signed-by=%s] %s spaced-testing main\n' "$KEY" "$REPOSITORY" > "$WORK/testing.list"
install -Dm0644 "$WORK/testing.list" "$SOURCE"
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
APT_OPTIONS=(-o APT::Update::Error-Mode=any -o Acquire::Retries=3
    -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30
    -o DPkg::Lock::Timeout=120 -o Dpkg::Use-Pty=0
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
apt-get "${APT_OPTIONS[@]}" update
# sed keeps this parseable without awk; the boot test rootfs does not bind /etc.
candidate=$(apt-cache policy spaced-meta | sed -n 's/^ *Candidate: *//p' | head -n 1)
dpkg --compare-versions "$candidate" ge 9.26 || {
    echo "Testing repository did not offer Spaced9.26 or newer: $candidate" >&2; exit 1;
}
apt-get "${APT_OPTIONS[@]}" --simulate --no-remove install spaced-meta | tee "$WORK/plan"
if grep -Eq '^Inst (systemd|systemd-sysv|runit-init|openrc)(:[^ ]+)? ' "$WORK/plan"; then
    echo 'Testing upgrade would change the supported init system; refusing.' >&2; exit 1
fi
# Retain the selected repository once package changes start so a failed
# configuration can be retried against the same signed source.
KEEP_SOURCE=1
dpkg --force-confdef --force-confold --configure --pending
apt-get "${APT_OPTIONS[@]}" -y --download-only --no-remove install spaced-meta
apt-get "${APT_OPTIONS[@]}" -y --no-remove install spaced-meta
# The settings package also owns this file. Preserve an explicitly supplied
# test-server URL for the rest of this transaction.
install -Dm0644 "$WORK/testing.list" "$SOURCE"
/bin/true  # Source is now stable; the helper takes the same transaction lock.
exec 9>&-
/usr/lib/spaced-linux/spaced-update-helper all

caller_uid=${SUDO_UID:-${PKEXEC_UID:-}}
if [[ "$caller_uid" =~ ^[0-9]+$ && "$caller_uid" != 0 ]]; then
    caller_name=$(getent passwd "$caller_uid" | cut -d: -f1)
    [[ -n "$caller_name" ]] || { echo 'Cannot identify the calling desktop user.' >&2; exit 1; }
    runuser -u "$caller_name" -- env XDG_RUNTIME_DIR="/run/user/$caller_uid" \
        flatpak update --noninteractive -y --user
else
    echo 'Run Spaced Update as each desktop user to update their private Flatpaks.'
fi
echo 'Signed testing upgrade completed. Reboot to use the updated kernel and desktop.'
