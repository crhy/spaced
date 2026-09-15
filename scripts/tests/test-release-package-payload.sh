#!/bin/bash
# Inspect built packages; no maintainer scripts execute on the host.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
REPO=${1:?Usage: test-release-package-payload.sh SIGNED_REPO}
SUITE=${SPACED_APT_SUITE:-spaced}
[[ "$SUITE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || exit 2
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
VERSION=$(sed -n 's/^Version: //p' "$ROOT/packages/spaced-meta/DEBIAN/control")
WALLPAPERS_VERSION=$(sed -n 's/^Version: //p' "$ROOT/packages/spaced-wallpapers/DEBIAN/control")
PACKAGES="$REPO/dists/$SUITE/main/binary-amd64"
dpkg-deb -e "$PACKAGES/spaced-meta_${VERSION}_all.deb" "$WORK/meta"
dpkg-deb -x "$PACKAGES/spaced-mate-default-settings_${VERSION}_all.deb" "$WORK/settings"
dpkg-deb -x "$PACKAGES/spaced-themes_${VERSION}_all.deb" "$WORK/themes"
dpkg-deb -x "$PACKAGES/spaced-wallpapers_${WALLPAPERS_VERSION}_all.deb" "$WORK/wallpapers"
python3 - "$ROOT" "$WORK" <<'PY'
from pathlib import Path
import re
import sys
import yaml
root, work = map(Path, sys.argv[1:])
control = (work / 'meta/control').read_text()
groups = yaml.safe_load((root / 'config/packages.yaml').read_text())
expected = {p for group, packages in groups.items() if group not in {'installer', 'live'} for p in packages}
expected |= {'linux-image-amd64', 'linux-headers-amd64', 'sysvinit-core', 'devuan-keyring', 'mate-session-manager'}
actual = {p.strip().split()[0] for p in re.search(r'^Depends: (.+)$', control, re.M)[1].split(',')}
assert not expected - actual, f'Missing runtime dependencies: {sorted(expected - actual)}'
assert not {'calamares', 'calamares-settings-debian', 'live-boot', 'live-config', 'live-config-sysvinit', 'openssh-server'} & actual
payload = work / 'settings'
themes = work / 'themes'
wallpapers = work / 'wallpapers'
for path in ('usr/local/bin/install-spaced-linux', 'usr/local/bin/spaced-live-session',
             'etc/skel/Desktop/install-spaced-linux.desktop',
             'usr/share/spaced-themes/cairo-dock/launchers/04-install.desktop'):
    assert not (payload / path).exists(), f'Live-only entrypoint delivered by upgrade: {path}'
    assert not (themes / path).exists(), f'Live-only entrypoint delivered by upgrade: {path}'
    assert not (wallpapers / path).exists(), f'Live-only entrypoint delivered by upgrade: {path}'
for path in ('usr/lib/spaced-linux/spaced-update.py', 'usr/lib/spaced-linux/spaced-update-helper',
             'usr/lib/spaced-linux/spaced-update-apt-guard',
             'usr/share/keyrings/spaced-archive-keyring.gpg', 'etc/apt/sources.list.d/spaced-apt.list',
             'etc/lightdm/lightdm.conf.d/60-spaced-installed.conf',
             'etc/X11/xorg.conf.d/20-spaced-amdgpu.conf', 'usr/local/bin/spaced-graphics-report',
             'etc/xdg/autostart/spaced-desktop-icon-repair-before-caja.desktop',
             'etc/xdg/autostart/spaced-desktop-icon-repair.desktop',
             'usr/local/sbin/spaced-sync-time', 'usr/local/sbin/spaced-finalize-timezone'):
    assert (payload / path).read_bytes() == (root / 'overlays' / path).read_bytes(), f'Missing/stale overlay: {path}'
for path in ('postinst', 'triggers'):
    assert (work / 'meta' / path).read_bytes() == (root / 'packages/spaced-meta/DEBIAN' / path).read_bytes(), f'Stale release maintainer script: {path}'
for path in ('usr/share/backgrounds/spaced/spaced-orbit-4k.png',
             'usr/share/mate-background-properties/spaced-linux.xml'):
    assert (wallpapers / path).read_bytes() == (root / 'overlays' / path).read_bytes(), f'Missing/stale wallpaper: {path}'
    assert not (payload / path).exists(), f'Wallpaper payload duplicated in settings: {path}'
for path in ('usr/share/spaced-themes/themes.json',
             'boot/grub/themes/spaced/theme.txt'):
    assert (themes / path).read_bytes() == (root / 'overlays' / path).read_bytes(), f'Missing/stale theme payload: {path}'
    assert not (payload / path).exists(), f'Theme payload duplicated in settings: {path}'
for path in ('usr/share/icons/Spaced-Icons-Linux-Dark/index.theme',):
    assert (themes / path).is_file(), f'Missing theme payload: {path}'
    assert not (payload / path).exists(), f'Theme payload duplicated in settings: {path}'
lightdm = (payload / 'etc/lightdm/lightdm.conf.d/60-spaced-installed.conf').read_text()
assert re.search(r'\[LightDM\](?:(?!\[).)*minimum-vt=1', lightdm, re.S), 'Upgrade omitted boot VT fix'
assert not re.search(r'^autologin-user=.+', lightdm, re.M), 'Installed defaults must not enable a test/live account'
source = (payload / 'etc/apt/sources.list.d/spaced-apt.list').read_text()
assert 'trusted=yes' not in source
assert 'signed-by=/usr/share/keyrings/spaced-archive-keyring.gpg' in source
preferences = '\n'.join(p.read_text() for p in (payload / 'etc/apt/preferences.d').iterdir() if p.is_file())
assert 'systemd-sysv' in preferences and 'Pin-Priority: -1' in preferences
print(f'Package payload and {len(expected)} runtime dependency checks passed.')
PY
