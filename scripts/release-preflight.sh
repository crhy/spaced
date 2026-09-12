#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG=${SPACED_EXTERNAL_ARTIFACT_CONFIG:-$ROOT/config/external-artifacts.conf}

die() {
    printf 'release-preflight: %s\n' "$*" >&2
    exit 1
}

[[ -r $CONFIG ]] || die "cannot read artifact configuration: $CONFIG"
# shellcheck disable=SC1090
. "$CONFIG"

require_digest() {
    local name=$1 value=$2 length=$3
    [[ $value =~ ^[[:xdigit:]]{$length}$ ]] ||
        die "$name is not pinned to a released artifact"
}

require_digest SPACED_WELCOME_SHA256 "$SPACED_WELCOME_SHA256" 64
require_digest SPACED_GITHUB_REMOTE_SHA256 "$SPACED_GITHUB_REMOTE_SHA256" 64
require_digest SPACED_GITHUB_GPG_FINGERPRINT "$SPACED_GITHUB_GPG_FINGERPRINT" 40
[[ $SPACED_WELCOME_RELEASE_TAG == "v$SPACED_WELCOME_VERSION" ]] ||
    die "Welcome tag '$SPACED_WELCOME_RELEASE_TAG' does not match version '$SPACED_WELCOME_VERSION'"

welcome_version_file=$ROOT/components/spacedwelcome/VERSION
if [[ -f $welcome_version_file ]]; then
    welcome_source_version=$(<"$welcome_version_file")
    [[ $welcome_source_version == "$SPACED_WELCOME_VERSION" ]] ||
        die "Welcome source version '$welcome_source_version' does not match '$SPACED_WELCOME_VERSION'"
fi

printf 'Release inputs are pinned for Spaced Linux %s\n' "$(<"$ROOT/VERSION")"
