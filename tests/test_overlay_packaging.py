"""Every overlay file reaches upgraded systems through a local package, or is
explicitly ISO-only.

11.26.4 shipped the GPU Manager and Sound Manager programs in the update
package but not their icon folders, so machines upgraded with Spaced Update
showed a missing-icon symbol everywhere (crhy/spaced#439). A new overlay file
must now be either listed in scripts/iso/build-local-packages.sh or added to
ISO_ONLY below with a reason.
"""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAYS = ROOT / 'overlays'
BUILDER = ROOT / 'scripts' / 'iso' / 'build-local-packages.sh'

# Prefixes that are installer/boot/live-image only, or packaged by a loop.
ISO_ONLY_PREFIXES = (
    'etc/calamares/',            # installer configuration, live image only
    'boot/grub/',                # boot theme, live image only
    'usr/share/themes/Spaced-',  # packaged by the themes loop in the builder
)
# Single files that stay ISO-only. Review before adding: an upgraded system
# never receives these.
ISO_ONLY = {
    'etc/machine-id', 'etc/issue', 'etc/issue.net', 'etc/os-release',
    'etc/lsb-release', 'etc/default/grub', 'etc/lightdm/lightdm.conf',
    'etc/lightdm/lightdm-gtk-greeter.conf',
    'etc/polkit-1/rules.d/49-spaced-live-gparted.rules',
    'etc/xdg/autostart/spaced-live-session.desktop',
    'etc/modprobe.d/spaced-live-nvidia.conf',
    # Found unpackaged when this test was written (2026-11-26); review whether
    # upgraded systems need them (crhy/spaced#439, #436).
    'etc/xdg/autostart/mate-volume-control-status-icon.desktop',
    'etc/xdg/autostart/localsearch-3.desktop',
    'usr/share/applications/spaced-suggest-qbittorrent.desktop',
}


def packaged_paths():
    text = BUILDER.read_text(encoding='utf-8')
    return set(re.findall(r'((?:etc|usr|var|lib|opt|boot)/[A-Za-z0-9._/+-]+)', text))


class OverlayPackagingTests(unittest.TestCase):
    def test_every_overlay_file_is_packaged_or_iso_only(self):
        paths = packaged_paths()
        missing = []
        for root, _dirs, files in os.walk(OVERLAYS):
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), OVERLAYS)
                if rel in ISO_ONLY or rel.startswith(ISO_ONLY_PREFIXES):
                    continue
                if not any(rel == p or rel.startswith(p.rstrip('/') + '/') for p in paths):
                    missing.append(rel)
        self.assertEqual(missing, [], 'overlay files no update package ships '
                         '(add them to build-local-packages.sh or ISO_ONLY): '
                         + ', '.join(sorted(missing)[:20]))

    def test_gpu_and_sound_manager_assets_are_packaged(self):
        paths = packaged_paths()
        for needed in ('usr/share/spaced-gpu-manager', 'usr/share/spaced-sound-manager',
                       'usr/share/applications/spaced-sound-manager.desktop'):
            self.assertIn(needed, paths)

    def test_no_package_overwrites_a_debian_owned_desktop_file(self):
        # dpkg refuses to overwrite another package's file; Spaced overrides of
        # MATE desktop entries live in /usr/local/share/applications instead.
        self.assertFalse((OVERLAYS / 'usr/share/applications/mate-volume-control.desktop').exists())
        self.assertTrue((OVERLAYS / 'usr/local/share/applications/mate-volume-control.desktop').exists())


if __name__ == '__main__':
    unittest.main()
