#!/bin/bash
# Isolate the desktop backport and nm-applet focus module build dependencies from the
# developer's operating system.
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
    apt-get install -y --no-install-recommends build-essential ca-certificates curl dpkg-dev \
        pkg-config libgtk-3-dev
chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
    apt-get build-dep -y --no-install-recommends marco
if ! "$ROOT/scripts/iso/stage-marco.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
        bash /workspace/scripts/iso/build-marco.sh --build /workspace/build/marco
fi
chroot "$CHROOT" bash /workspace/scripts/iso/build-nm-focus.sh /workspace/build/nm-focus
# The Compiz decorator fix (issue #279) is built in the same chroot.
if ! "$ROOT/scripts/iso/stage-compiz.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        apt-get build-dep -y --no-install-recommends compiz
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
        bash /workspace/scripts/iso/build-compiz.sh --build /workspace/build/compiz
fi
# Enhanced Zoom must consume XI2 scrolling before it reaches Qt clients (#371).
if ! "$ROOT/scripts/iso/stage-compiz-plugins-main.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        apt-get build-dep -y --no-install-recommends compiz-plugins-main
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
        bash /workspace/scripts/iso/build-compiz-plugins-main.sh --build /workspace/build/compiz-plugins-main
fi
# The X server with the amdgpu ABI fix (issue #298) is built here as well.
if ! "$ROOT/scripts/iso/stage-xorg-server.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        apt-get build-dep -y --no-install-recommends xorg-server
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=4 \
        bash /workspace/scripts/iso/build-xorg-server.sh --build /workspace/build/xorg-server
fi
# Caja's upstream fix preserves a renamed destination in cross-filesystem moves.
if ! "$ROOT/scripts/iso/stage-caja.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        apt-get build-dep -y --no-install-recommends caja
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
        bash /workspace/scripts/iso/build-caja.sh --build /workspace/build/caja
fi
# Brisk's context menu is extended with Spaced package and launcher actions.
if ! "$ROOT/scripts/iso/stage-brisk-menu.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        apt-get build-dep -y --no-install-recommends brisk-menu
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
        bash /workspace/scripts/iso/build-brisk-menu.sh --build /workspace/build/brisk-menu
fi
# MATE's shortcut editor uses desktop IDs and can select arbitrary files.
if ! "$ROOT/scripts/iso/stage-mate-control-center.sh" --check 2>/dev/null; then
    chroot "$CHROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive \
        apt-get build-dep -y --no-install-recommends mate-control-center
    chroot "$CHROOT" /usr/bin/env DEB_BUILD_OPTIONS=parallel=2 \
        bash /workspace/scripts/iso/build-mate-control-center.sh --build /workspace/build/mate-control-center
fi
if [ -n "${PKEXEC_UID:-}" ]; then
    chown -R "$PKEXEC_UID" "$ROOT/build/marco/artifacts" "$ROOT/build/nm-focus" "$ROOT/build/compiz" \
        "$ROOT/build/compiz-plugins-main" "$ROOT/build/xorg-server" "$ROOT/build/caja" "$ROOT/build/brisk-menu" \
        "$ROOT/build/mate-control-center"
fi
