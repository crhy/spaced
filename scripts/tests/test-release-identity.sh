#!/bin/bash
# Exercise the real postinst and file triggers with dpkg in an unprivileged
# user namespace. Host binaries/libraries are read-only; /etc and dpkg state
# are temporary, with no host mounts writable and no network access.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
VERSION=$(sed -n 's/^Version: //p' "$ROOT/packages/spaced-meta/DEBIAN/control")
mkdir -p "$WORK/root"/{etc,var/lib/dpkg/info,var/lib/dpkg/updates,var/lib/dpkg/triggers,var/log,usr/lib,usr/share,packages}
: > "$WORK/root/var/lib/dpkg/status"
printf 'root:x:0:0:root:/root:/bin/sh\n' > "$WORK/root/etc/passwd"
printf 'root:x:0:\n' > "$WORK/root/etc/group"
ln -s usr/bin "$WORK/root/bin"
ln -s usr/lib "$WORK/root/lib"
ln -s usr/sbin "$WORK/root/sbin"

base_fixture() {
    local version=$1 stage="$WORK/base-$1"
    mkdir -p "$stage/DEBIAN" "$stage/usr/lib" "$stage/etc"
    cat > "$stage/DEBIAN/control" <<EOF
Package: base-files
Version: $version
Architecture: all
Maintainer: Upgrade Test <test@localhost>
Description: Temporary upstream identity fixture
EOF
    printf 'NAME="Devuan GNU/Linux"\nVERSION_ID="%s"\n' "$version" > "$stage/usr/lib/os-release"
    ln -s ../usr/lib/os-release "$stage/etc/os-release"
    printf 'DISTRIB_ID=Devuan\nDISTRIB_RELEASE=%s\n' "$version" > "$stage/etc/lsb-release"
    dpkg-deb --root-owner-group --build "$stage" "$WORK/root/packages/base-files_${version}_all.deb" >/dev/null
}
base_fixture 13
base_fixture 14
for version in 8.26.4 "$VERSION"; do
    stage="$WORK/meta-$version"
    mkdir -p "$stage/DEBIAN"
    cp "$ROOT/packages/spaced-meta/DEBIAN/"{postinst,triggers} "$stage/DEBIAN/"
    chmod 0755 "$stage/DEBIAN/postinst"
    # Only dependency control is reduced; exact production scripts/triggers
    # execute under dpkg. Full runtime resolution is tested separately.
    cat > "$stage/DEBIAN/control" <<EOF
Package: spaced-meta
Version: $version
Architecture: all
Maintainer: Upgrade Test <test@localhost>
Depends: base-files
Description: Temporary release script fixture
EOF
    dpkg-deb --root-owner-group --build "$stage" "$WORK/root/packages/spaced-meta_${version}_all.deb" >/dev/null
done
cat > "$WORK/root/packages/test.sh" <<'INNER'
#!/bin/bash
set -euo pipefail
version=$1
os_version=${version%-*}
check_identity() {
    for marker in /etc/os-release /usr/lib/os-release; do
        grep -qx "VERSION_ID=\"$1\"" "$marker"
        grep -qx 'ID=spaced' "$marker"
    done
    grep -qx "DISTRIB_RELEASE=$1" /etc/lsb-release
    grep -q "Spaced Linux $1" /etc/issue
    grep -qx "Spaced Linux $1" /etc/issue.net
}
dpkg --install /packages/base-files_13_all.deb /packages/spaced-meta_8.26.4_all.deb
check_identity 8.26.4
dpkg --install "/packages/spaced-meta_${version}_all.deb"
check_identity "$os_version"
grep -qx "BUILD_ID=\"$version\"" /etc/os-release
# A later upstream unpack must invoke the production interest-noawait trigger.
dpkg --install /packages/base-files_14_all.deb
check_identity "$os_version"
grep -qx "BUILD_ID=\"$version\"" /etc/os-release
# Direct trigger replay must be idempotent and leave no pending package state.
dpkg-trigger --no-await --by-package=base-files /usr/lib/os-release
dpkg --triggers-only --pending
check_identity "$os_version"
grep -qx "BUILD_ID=\"$version\"" /etc/os-release
[[ -z $(dpkg --audit) ]]
echo "Real dpkg identity upgrade and base-files trigger tests passed ($version)."
INNER
bwrap --die-with-parent --unshare-all --uid 0 --gid 0 \
    --setenv PATH /usr/sbin:/usr/bin:/sbin:/bin \
    --bind "$WORK/root" / \
    --ro-bind /usr/bin /usr/bin \
    --ro-bind /usr/sbin /usr/sbin \
    --ro-bind /usr/lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu \
    --ro-bind /lib64 /lib64 \
    --ro-bind /usr/share/dpkg /usr/share/dpkg \
    --proc /proc --dev /dev --tmpfs /tmp \
    /bin/bash /packages/test.sh "$VERSION"
