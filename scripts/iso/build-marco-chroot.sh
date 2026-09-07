#!/bin/bash
# Isolate the Marco build dependencies from the developer's operating system.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CHROOT="$ROOT/build/marco/chroot"
MIRROR=${SPACED_DEVUAN_MIRROR:-http://mirror.hootsoftware.com/devuan/merged}
KEYRING=/usr/share/keyrings/devuan-archive-keyring.pgp
[ -f "$KEYRING" ] || KEYRING="$ROOT/config/keyrings/devuan-archive-keyring.pgp"
if [ "$(id -u)" -ne 0 ]; then
    exec pkexec bash "$ROOT/scripts/iso/build-marco-chroot.sh" "$@"
fi
if [ "${1:-}" != --inside ]; then
    exec unshare --mount --propagation private -- bash "$ROOT/scripts/iso/build-marco-chroot.sh" --inside
fi
mkdir -p "$ROOT/build/marco"
if [ ! -f "$CHROOT/.spaced-bootstrap-complete" ]; then
    debootstrap --keyring="$KEYRING" \
        --variant=minbase ceres "$CHROOT" "$MIRROR" sid
    touch "$CHROOT/.spaced-bootstrap-complete"
fi

cleanup() {
    for mountpoint in "$CHROOT/workspace" "$CHROOT/proc" "$CHROOT/sys" "$CHROOT/dev"; do
        umount --recursive "$mountpoint" 2>/dev/null || true
    done
}
trap cleanup EXIT
mkdir -p "$CHROOT"/{dev,proc,sys,workspace}
mount --rbind /dev "$CHROOT/dev"
mount --make-rslave "$CHROOT/dev"
mount -t proc proc "$CHROOT/proc"
mount --rbind /sys "$CHROOT/sys"
mount --make-rslave "$CHROOT/sys"
mount --bind "$ROOT" "$CHROOT/workspace"
printf '#!/bin/sh\nexit 101\n' > "$CHROOT/usr/sbin/policy-rc.d"
chmod 755 "$CHROOT/usr/sbin/policy-rc.d"
install -Dm0644 "$KEYRING" "$CHROOT/usr/share/keyrings/spaced-devuan-build.pgp"
cat > "$CHROOT/etc/apt/sources.list" <<EOF
deb [signed-by=/usr/share/keyrings/spaced-devuan-build.pgp] $MIRROR ceres main
deb-src [signed-by=/usr/share/keyrings/spaced-devuan-build.pgp] $MIRROR ceres main
EOF
cp -L /etc/resolv.conf "$CHROOT/etc/resolv.conf"
chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
    apt-get -o APT::Update::Error-Mode=any update
chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends build-essential ca-certificates curl dpkg-dev
chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
    apt-get build-dep -y --no-install-recommends marco
chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
    bash /workspace/scripts/iso/build-marco.sh --build /workspace/build/marco
if [ -n "${PKEXEC_UID:-}" ]; then
    chown -R "$PKEXEC_UID" "$ROOT/build/marco/artifacts"
fi
