#!/bin/bash
# Inspect built packages; no maintainer scripts execute on the host.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
REPO=${1:?Usage: test-release-package-payload.sh SIGNED_REPO}
SUITE=${SPACED_APT_SUITE:-spaced-testing}
[[ "$SUITE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || exit 2
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT
VERSION=$(sed -n 's/^Version: //p' "$ROOT/packages/spaced-meta/DEBIAN/control")
PACKAGES="$REPO/dists/$SUITE/main/binary-amd64"
dpkg-deb -e "$PACKAGES/spaced-meta_${VERSION}_all.deb" "$WORK/meta"
dpkg-deb -x "$PACKAGES/spaced-mate-default-settings_${VERSION}_all.deb" "$WORK/settings"
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
for path in ('usr/local/bin/install-spaced-linux', 'usr/local/bin/spaced-live-session',
             'etc/skel/Desktop/install-spaced-linux.desktop',
             'usr/share/spaced-themes/cairo-dock/launchers/04-install.desktop'):
    assert not (payload / path).exists(), f'Live-only entrypoint delivered by upgrade: {path}'
for path in ('usr/lib/spaced-linux/spaced-update.py', 'usr/lib/spaced-linux/spaced-update-helper',
             'usr/share/keyrings/spaced-archive-keyring.gpg', 'etc/apt/sources.list.d/spaced-apt.list',
             'etc/X11/xorg.conf.d/20-spaced-amdgpu.conf', 'usr/local/bin/spaced-graphics-report',
             'usr/local/sbin/spaced-sync-time', 'usr/local/sbin/spaced-finalize-timezone'):
    assert (payload / path).read_bytes() == (root / 'overlays' / path).read_bytes(), f'Missing/stale overlay: {path}'
for path in ('postinst', 'triggers'):
    assert (work / 'meta' / path).read_bytes() == (root / 'packages/spaced-meta/DEBIAN' / path).read_bytes(), f'Stale release maintainer script: {path}'
source = (payload / 'etc/apt/sources.list.d/spaced-apt.list').read_text()
assert 'trusted=yes' not in source
assert 'signed-by=/usr/share/keyrings/spaced-archive-keyring.gpg' in source
preferences = '\n'.join(p.read_text() for p in (payload / 'etc/apt/preferences.d').iterdir() if p.is_file())
assert 'systemd-sysv' in preferences and 'Pin-Priority: -1' in preferences
print(f'Package payload and {len(expected)} runtime dependency checks passed.')
PY
