#!/bin/bash
# Resolve the complete current desktop from a clean or historical dpkg status.
# All APT state lives in a temporary directory; the host is never upgraded.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=${1:?Usage: test-upgrade-packages.sh SIGNED_REPO [DPKG_STATUS ...]}
shift
[[ "$#" -gt 0 ]] || set -- /dev/null
SUITE=${SPACED_APT_SUITE:-spaced-testing}
[[ "$SUITE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo 'Invalid APT suite.' >&2; exit 1; }
REPO=$(realpath "$REPO")
[[ -f "$REPO/dists/$SUITE/InRelease" ]] || { echo "Build the signed $SUITE APT repository first." >&2; exit 1; }
for status in "$@"; do [[ -f "$status" || "$status" == /dev/null ]]; done
workspace=$(mktemp -d)
trap 'rm -rf "$workspace"' EXIT
mkdir -p "$workspace/lists/partial" "$workspace/archives/partial" "$workspace/empty"
: > "$workspace/status"
cat > "$workspace/sources.list" <<EOF
deb [signed-by=$ROOT/config/keyrings/devuan-archive-keyring.pgp] http://mirror.hootsoftware.com/devuan/merged ceres main contrib non-free non-free-firmware
deb [signed-by=$ROOT/overlays/usr/share/keyrings/spaced-archive-keyring.gpg] file:$REPO $SUITE main
EOF
cat > "$workspace/apt.conf" <<EOF
Dir::Etc::main "/dev/null";
Dir::Etc::parts "$workspace/empty";
Dir::Etc::sourcelist "$workspace/sources.list";
Dir::Etc::sourceparts "$workspace/empty";
Dir::Etc::preferences "/dev/null";
Dir::Etc::preferencesparts "$ROOT/overlays/etc/apt/preferences.d";
Dir::State "$workspace";
Dir::State::status "$workspace/status";
Dir::State::lists "$workspace/lists";
Dir::Cache "$workspace";
Dir::Cache::archives "$workspace/archives";
Dir::Cache::pkgcache "";
Dir::Cache::srcpkgcache "";
APT::Architecture "amd64";
APT::Architectures { "amd64"; };
APT::Sandbox::User "$(id -un)";
APT::Install-Recommends "false";
APT::Update::Error-Mode "any";
Acquire::Retries "3";
Acquire::http::Timeout "30";
EOF
# Include any foreign architectures installed in the supplied historical
# states; a multiarch upgrade must resolve those libraries too.
awk '/^Architecture:/ && $2 != "all" && $2 != "amd64" {print $2}' "$@" | sort -u |
    while read -r architecture; do
        [[ "$architecture" =~ ^[a-z0-9-]+$ ]] || exit 1
        printf 'APT::Architectures:: "%s";\n' "$architecture"
    done >> "$workspace/apt.conf"
export APT_CONFIG=$workspace/apt.conf
apt-get update
apt-cache policy spaced-meta spaced-mate-default-settings spaced-welcome \
    linux-image-amd64 linux-headers-amd64 libmarco-private2 amdgpu-top
candidate=$(apt-cache policy spaced-meta | awk '/Candidate:/ {print $2; exit}')
[[ "$candidate" == "$(sed -n 's/^Version: //p' "$ROOT/packages/spaced-meta/DEBIAN/control")" ]] || { echo "Wrong release candidate: $candidate" >&2; exit 1; }
for status in "$@"; do
    cp "$status" "$workspace/status"
    printf '\nResolving full rolling upgrade from %s\n' "$status"
    installed=$(dpkg-query --admindir="$workspace" -W -f='${db:Status-Status} ${Version}' spaced-meta 2>/dev/null || true)
    # Supplying the release metapackage also covers earliest installations
    # which did not carry it. Checking only "install spaced-meta" misses the
    # other upgrades and rolling dependency transitions on an old system.
    apt-get --simulate dist-upgrade spaced-meta | tee "$workspace/plan"
    if [[ "$installed" != "installed $candidate" ]] && ! grep -Eq '^Inst spaced-meta(:[^ ]+)? ' "$workspace/plan"; then
        echo "Upgrade plan did not install the target metapackage from: ${installed:-absent}." >&2
        exit 1
    fi
    if grep -Eq '^(Remv (sysvinit-core|sysvinit-utils|initscripts|spaced-meta|spaced-mate-default-settings|mate-session-manager|mate-panel|caja|compiz|lightdm|network-manager|apt|dpkg|flatpak)(:[^ ]+)? |Inst (systemd|systemd-sysv|runit-init|openrc)(:[^ ]+)? )' "$workspace/plan"; then
        echo 'Upgrade plan removes the supported desktop or changes init systems.' >&2
        exit 1
    fi
    removals=$(awk '/^Remv / {print $2}' "$workspace/plan")
    if [[ -n "$removals" ]]; then
        printf 'Review rolling-transition removals (core-package guard passed):\n%s\n' "$removals"
    fi
    held=$(apt-mark showhold)
    [[ -z "$held" ]] || printf 'Administrator holds remain in effect:\n%s\n' "$held"
    echo "Signed full-upgrade resolution passed: $status"
done
echo 'All supplied package states passed. These are solver tests, not boot tests.'
