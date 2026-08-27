#!/bin/bash
# Stage independently released, checksum-pinned components for the ISO.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CONFIG=${SPACED_EXTERNAL_ARTIFACT_CONFIG:-$ROOT/config/external-artifacts.conf}
IMAGE_ROOT=${SPACED_IMAGE_ROOT:-$ROOT/build/live-build/config/includes.chroot}
LOCAL_PACKAGE_OUTPUT=${LOCAL_PACKAGE_OUTPUT:-$ROOT/build/local-packages}
STAGE_OUTPUT=${SPACED_EXTERNAL_STAGE_DIR:-$ROOT/build/external-artifacts}
CACHE=${SPACED_EXTERNAL_CACHE_DIR:-$ROOT/build/cache/external-artifacts}
TARGET_ARCH=${SPACED_TARGET_ARCH:-$(dpkg --print-architecture)}

die() {
    printf 'stage-external-artifacts: %s\n' "$*" >&2
    exit 1
}

[[ -r $CONFIG ]] || die "cannot read artifact configuration: $CONFIG"
# shellcheck disable=SC1090
. "$CONFIG"

case $TARGET_ARCH in
    amd64|x86_64)
        DEB_ARCH=amd64
        FLATPAK_ARCH=x86_64
        BAZAAR_CONFIGURED_SHA=$SPACED_BAZAAR_SHA256_AMD64
        ;;
    arm64|aarch64)
        DEB_ARCH=arm64
        FLATPAK_ARCH=aarch64
        BAZAAR_CONFIGURED_SHA=$SPACED_BAZAAR_SHA256_ARM64
        ;;
    *)
        die "unsupported target architecture '$TARGET_ARCH' (expected amd64 or arm64)"
        ;;
esac

WELCOME_FILENAME="spaced-welcome_${SPACED_WELCOME_VERSION}_all.deb"
BAZAAR_FILENAME="SpacedBazaar-${FLATPAK_ARCH}.flatpak"
WELCOME_URL=${SPACED_WELCOME_URL:-https://github.com/${SPACED_WELCOME_REPOSITORY}/releases/download/${SPACED_WELCOME_RELEASE_TAG}/${WELCOME_FILENAME}}
BAZAAR_URL=${SPACED_BAZAAR_URL:-https://github.com/${SPACED_BAZAAR_REPOSITORY}/releases/download/${SPACED_BAZAAR_RELEASE_TAG}/${BAZAAR_FILENAME}}
BAZAAR_SHA=${SPACED_BAZAAR_SHA256:-$BAZAAR_CONFIGURED_SHA}

for command in awk base64 cp curl dpkg-deb gpg install mktemp mv sha256sum; do
    command -v "$command" >/dev/null 2>&1 || die "required host command is missing: $command"
done

work=$(mktemp -d)
cleanup() {
    rm -rf -- "$work"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$IMAGE_ROOT/usr/share/spaced-linux/bootstrap" \
    "$LOCAL_PACKAGE_OUTPUT" "$STAGE_OUTPUT" "$CACHE"

validate_sha256() {
    local label=$1 expected=$2
    [[ $expected =~ ^[[:xdigit:]]{64}$ ]] ||
        die "$label is not released: set its 64-character SHA-256 in $CONFIG or the environment"
}

verify_sha256() {
    local label=$1 path=$2 expected=${3,,}
    local actual
    actual=$(sha256sum "$path" | awk '{print $1}')
    [[ $actual == "$expected" ]] ||
        die "$label checksum mismatch: expected $expected, got $actual"
}

# Sets MATERIALIZED to a verified local/cache path. A local override never
# bypasses verification; pass its digest through the corresponding SHA value.
materialize() {
    local label=$1 url=$2 override=$3 expected=$4 cache_name=$5
    local candidate partial

    validate_sha256 "$label" "$expected"
    if [[ -n $override ]]; then
        [[ -f $override ]] || die "$label local override does not exist: $override"
        verify_sha256 "$label" "$override" "$expected"
        MATERIALIZED=$override
        return
    fi

    [[ $url == https://* ]] || die "$label URL must use HTTPS: $url"
    [[ $url != *UNRELEASED* ]] ||
        die "$label release is not published; set a release tag or use a verified local override"
    candidate="$CACHE/$cache_name"
    if [[ -f $candidate ]]; then
        if verify_sha256 "$label cached artifact" "$candidate" "$expected"; then
            MATERIALIZED=$candidate
            return
        fi
    fi

    partial="$work/$cache_name"
    printf 'Downloading %s from %s\n' "$label" "$url"
    curl --fail --location --show-error \
        --proto '=https' --proto-redir '=https' \
        --retry 3 --retry-all-errors --connect-timeout 15 \
        --output "$partial" "$url"
    verify_sha256 "$label" "$partial" "$expected"
    install -m0644 "$partial" "$candidate.tmp.$$"
    mv -f "$candidate.tmp.$$" "$candidate"
    MATERIALIZED=$candidate
}

install_atomic() {
    local source=$1 destination=$2
    install -m0644 "$source" "$destination.tmp.$$"
    mv -f "$destination.tmp.$$" "$destination"
}

materialize \
    "spaced-welcome $SPACED_WELCOME_VERSION" \
    "$WELCOME_URL" "${SPACED_WELCOME_DEB:-}" "$SPACED_WELCOME_SHA256" \
    "spaced-welcome-${SPACED_WELCOME_VERSION}-${SPACED_WELCOME_SHA256,,}.deb"
welcome_source=$MATERIALIZED
welcome_package=$(dpkg-deb -f "$welcome_source" Package)
welcome_version=$(dpkg-deb -f "$welcome_source" Version)
welcome_arch=$(dpkg-deb -f "$welcome_source" Architecture)
[[ $welcome_package == spaced-welcome ]] ||
    die "Welcome artifact package is '$welcome_package', expected 'spaced-welcome'"
[[ $welcome_version == "$SPACED_WELCOME_VERSION" ]] ||
    die "Welcome artifact version is '$welcome_version', expected '$SPACED_WELCOME_VERSION'"
[[ $welcome_arch == all || $welcome_arch == "$DEB_ARCH" ]] ||
    die "Welcome artifact architecture '$welcome_arch' is incompatible with '$DEB_ARCH'"
welcome_destination="$LOCAL_PACKAGE_OUTPUT/spaced-welcome_${SPACED_WELCOME_VERSION}_${welcome_arch}.deb"
find "$LOCAL_PACKAGE_OUTPUT" -maxdepth 1 -type f -name 'spaced-welcome_*.deb' \
    ! -name "$(basename "$welcome_destination")" -delete
install_atomic "$welcome_source" "$welcome_destination"

materialize \
    "SpacedBazaar $SPACED_BAZAAR_VERSION ($FLATPAK_ARCH)" \
    "$BAZAAR_URL" "${SPACED_BAZAAR_BUNDLE:-}" "$BAZAAR_SHA" \
    "SpacedBazaar-${SPACED_BAZAAR_VERSION}-${FLATPAK_ARCH}-${BAZAAR_SHA,,}.flatpak"
bazaar_source=$MATERIALIZED
[[ -s $bazaar_source ]] || die "SpacedBazaar bundle is empty"
install_atomic "$bazaar_source" \
    "$IMAGE_ROOT/usr/share/spaced-linux/bootstrap/SpacedBazaar.flatpak"

materialize \
    "spaced-github Flatpak remote" \
    "$SPACED_GITHUB_REMOTE_DESCRIPTOR_URL" "${SPACED_GITHUB_REMOTE_FILE:-}" \
    "$SPACED_GITHUB_REMOTE_SHA256" \
    "spaced-github-${SPACED_GITHUB_REMOTE_SHA256,,}.flatpakrepo"
remote_source=$MATERIALIZED

[[ $(awk '/^\[Flatpak Repo\]$/{count++} END{print count+0}' "$remote_source") == 1 ]] ||
    die "spaced-github descriptor is not a Flatpak Repo definition"
descriptor_repo_url=$(awk -F= '/^Url=/{sub(/^Url=/, ""); print; exit}' "$remote_source")
[[ $descriptor_repo_url == "$SPACED_GITHUB_REPO_URL" ]] ||
    die "spaced-github descriptor URL is '$descriptor_repo_url', expected '$SPACED_GITHUB_REPO_URL'"
descriptor_key=$(awk -F= '/^GPGKey=/{sub(/^GPGKey=/, ""); print; exit}' "$remote_source")
[[ -n $descriptor_key && $descriptor_key != UNRELEASED ]] ||
    die "spaced-github descriptor has no release signing key"
printf '%s' "$descriptor_key" | base64 --decode > "$work/spaced-github.gpg" 2>/dev/null ||
    die "spaced-github descriptor contains an invalid base64 signing key"
[[ $SPACED_GITHUB_GPG_FINGERPRINT =~ ^[[:xdigit:]]{40}$ ]] ||
    die "spaced-github signing-key fingerprint is unreleased or invalid"
mkdir -m0700 "$work/gnupg"
actual_fingerprint=$(GNUPGHOME="$work/gnupg" gpg --batch --show-keys --with-colons \
    "$work/spaced-github.gpg" 2>/dev/null |
    awk -F: '$1 == "fpr" {print toupper($10); exit}')
[[ $actual_fingerprint == "${SPACED_GITHUB_GPG_FINGERPRINT^^}" ]] ||
    die "spaced-github signing-key fingerprint mismatch: expected ${SPACED_GITHUB_GPG_FINGERPRINT^^}, got ${actual_fingerprint:-none}"
install_atomic "$remote_source" "$STAGE_OUTPUT/spaced-github.flatpakrepo"

printf 'Staged %s\n' "$welcome_destination"
printf 'Staged SpacedBazaar %s for system installation\n' "$SPACED_BAZAAR_VERSION"
printf 'Staged signed %s Flatpak remote\n' "$SPACED_GITHUB_REMOTE_NAME"
