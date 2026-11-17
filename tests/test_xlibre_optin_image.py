"""Issue #314: Xlibre is an opt-in test image that refuses an unpinned set.

The default image must keep installing Xorg, the opt-in set must refuse to
emit anything until every entry is pinned, and the Xorg ABI guard from issue
#298 must stay exactly as it was.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIST = ROOT / 'scripts/iso/package-list.sh'
OPTIN_LIST = ROOT / 'scripts/iso/xlibre-package-list.sh'
PACKAGES = ROOT / 'config/packages.yaml'
OPTIN_CONFIG = ROOT / 'config/xlibre-test-image.yaml'
PIN = ROOT / 'overlays/etc/apt/preferences.d/spaced-xorg-abi'
GUARD = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-apt-guard'
BROKEN = '2:21.1.25-1devuan1'
FIXED = '2:21.1.25-1devuan1+spaced10.26.3'
PINNED_SHA = '0123456789abcdef' * 4


def run(command, cwd=None, env=None):
    return subprocess.run(command, cwd=cwd and str(cwd), env=env,
                          capture_output=True, text=True, timeout=120)


def packages_from(output):
    return [line for line in output.splitlines() if line.strip()]


def write_fixture(temp, text):
    path = Path(temp) / 'xlibre-test-image.yaml'
    path.write_text(text, encoding='utf-8')
    return path


def run_optin(config_path):
    env = dict(PATH='/usr/bin:/bin', PYTHONDONTWRITEBYTECODE='1')
    env['SPACED_XLIBRE_IMAGE_CONFIG'] = str(config_path)
    return run(['bash', str(OPTIN_LIST)], env=env)


class DefaultImageTests(unittest.TestCase):
    def test_default_image_still_installs_xorg_and_no_xlibre(self):
        result = run(['bash', str(DEFAULT_LIST)], cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        emitted = packages_from(result.stdout)

        # scripts/iso/package-list.sh still emits exactly the union of every
        # group in config/packages.yaml, so this task cannot have changed it.
        groups = yaml.safe_load(PACKAGES.read_text(encoding='utf-8'))
        union = {package.strip() for values in groups.values() for package in values}
        self.assertEqual(sorted(emitted), sorted(union))
        self.assertEqual(len(emitted), len(union), 'duplicate packages emitted')

        # The graphics group (config/packages.yaml:58-71) is the Xorg stack.
        lines = PACKAGES.read_text(encoding='utf-8').splitlines()[57:71]
        graphics = [re.fullmatch(r'\s*-\s+(\S+)\s*', line).group(1)
                    for line in lines if re.fullmatch(r'\s*-\s+(\S+)\s*', line)]
        xorg = [package for package in graphics if package.startswith('xserver-xorg-')]
        self.assertEqual(sorted(xorg), sorted((
            'xserver-xorg-video-amdgpu', 'xserver-xorg-video-ati',
            'xserver-xorg-video-radeon', 'xserver-xorg-input-libinput',
            'xserver-xorg-video-intel', 'xserver-xorg-video-all',
            'xserver-xorg-video-nouveau', 'xserver-xorg-video-fbdev',
            'xserver-xorg-video-vesa')))
        for package in xorg:
            self.assertIn(package, emitted, f'default image lost {package}')
        self.assertNotIn('mesa-utils', xorg, 'mesa-utils is not an X server package')
        self.assertIn('mesa-utils', emitted)

        self.assertFalse([package for package in emitted if 'xlibre' in package],
                         'the default image must not carry an Xlibre package')


class OptInRefusalTests(unittest.TestCase):
    def committed_entries(self):
        data = yaml.safe_load(OPTIN_CONFIG.read_text(encoding='utf-8'))
        return [entry['package'] for entry in data['display_server']]

    def test_committed_optin_set_refuses_and_names_every_unpinned_entry(self):
        result = run(['bash', str(OPTIN_LIST)], cwd=ROOT)
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn('UNRELEASED', output)
        for package in self.committed_entries():
            self.assertIn(package, output, f'refusal did not name {package}')

    def test_a_short_sha256_still_refuses(self):
        text = OPTIN_CONFIG.read_text(encoding='utf-8').replace(
            'version: UNRELEASED', 'version: 1.0.0-1').replace(
            'sha256: UNRELEASED', f'sha256: {PINNED_SHA[:-1]}')
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, text))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('xlibre-server', result.stdout + result.stderr)
        self.assertIn('64-character', result.stdout + result.stderr)

    def test_a_missing_sha256_field_still_refuses(self):
        text = OPTIN_CONFIG.read_text(encoding='utf-8').replace(
            '    sha256: UNRELEASED', '', 1).replace(
            'version: UNRELEASED', 'version: 1.0.0-1')
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, text))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('xlibre-server', result.stdout + result.stderr)

    def test_the_xorg_fallback_boot_may_not_be_switched_off(self):
        text = OPTIN_CONFIG.read_text(encoding='utf-8').replace(
            'fallback_boot: xorg', 'fallback_boot: xlibre')
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, text))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fallback_boot', result.stdout + result.stderr)

    def test_only_xserver_xorg_packages_may_be_replaced(self):
        text = OPTIN_CONFIG.read_text(encoding='utf-8').replace(
            '  - xserver-xorg-video-vesa', '  - lightdm')
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, text))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('xserver-xorg-', result.stdout + result.stderr)

    def test_the_optin_script_never_edits_the_default_package_set(self):
        before = PACKAGES.read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            run_optin(write_fixture(temp, OPTIN_CONFIG.read_text(encoding='utf-8')))
        self.assertEqual(PACKAGES.read_bytes(), before)


class PinnedFixtureTests(unittest.TestCase):
    def pinned_text(self, **replacements):
        text = OPTIN_CONFIG.read_text(encoding='utf-8')
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text.replace('version: UNRELEASED', 'version: 1.0.0-1').replace(
            'sha256: UNRELEASED', f'sha256: {PINNED_SHA}')

    def test_a_fully_pinned_set_emits_the_reviewed_entries(self):
        data = yaml.safe_load(OPTIN_CONFIG.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, self.pinned_text()))
        self.assertEqual(result.returncode, 0, result.stderr)
        emitted = packages_from(result.stdout)
        expected = sorted([entry['package'] for entry in data['display_server']]
                          + data['fallback_packages'])
        self.assertEqual(emitted, expected)
        self.assertIn('xserver-xorg-core', emitted, 'rollback entry was dropped')

    def test_replaced_xorg_server_and_driver_entries_are_dropped(self):
        text = self.pinned_text()
        text = text.replace(
            'display_server:\n',
            'display_server:\n'
            '  - package: xserver-xorg-video-amdgpu\n'
            '    version: 1.0.0-1\n'
            f'    sha256: {PINNED_SHA}\n')
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, text))
        self.assertEqual(result.returncode, 0, result.stderr)
        emitted = packages_from(result.stdout)
        data = yaml.safe_load(OPTIN_CONFIG.read_text(encoding='utf-8'))
        for package in data['replaces']:
            self.assertNotIn(package, emitted, f'{package} was not replaced')
        self.assertNotIn('xserver-xorg-video-amdgpu', emitted)
        self.assertIn('xserver-xorg-core', emitted)

    def test_a_fallback_entry_cannot_be_replaced_silently(self):
        text = self.pinned_text().replace(
            '  - xserver-xorg-video-vesa', '  - xserver-xorg-core')
        with tempfile.TemporaryDirectory() as temp:
            result = run_optin(write_fixture(temp, text))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('xserver-xorg-core', result.stdout + result.stderr)

    def test_the_committed_matrix_claims_nothing_as_verified(self):
        data = yaml.safe_load(OPTIN_CONFIG.read_text(encoding='utf-8'))
        self.assertEqual(sorted(data['matrix']), sorted((
            'compiz-mate', 'mesa', 'nvidia', 'amd', 'intel', 'virtualbox',
            'qemu', 'multi-monitor-hotplug', 'suspend-reboot')))
        for row, value in data['matrix'].items():
            self.assertEqual(value['result'], 'pending', f'{row} claims a result')
        self.assertEqual(data['fallback_boot'], 'xorg')
        for entry in data['display_server']:
            self.assertEqual(entry['version'], 'UNRELEASED')
            self.assertEqual(entry['sha256'], 'UNRELEASED')


class AbiGuardUntouchedTests(unittest.TestCase):
    def transaction(self, *actions):
        return 'VERSION 2\nAPT::Architecture=amd64\n\n' + ''.join(
            f'{package} {old} < {new} /var/cache/apt/archives/{package}.deb\n'
            for package, old, new in actions)

    def test_guard_files_are_byte_unchanged(self):
        if not shutil.which('git'):
            self.skipTest('requires git')
        for path in (PIN, GUARD):
            relative = str(path.relative_to(ROOT))
            result = subprocess.run(['git', '-C', str(ROOT), 'show',
                                     f'origin/main:{relative}'],
                                    capture_output=True, timeout=60)
            if result.returncode != 0:
                self.skipTest('origin/main is not available to compare against')
            self.assertEqual(path.read_bytes(), result.stdout,
                             f'{relative} changed; the opt-in path may not touch '
                             'the Xorg ABI guard')

    def test_the_optin_path_still_refuses_the_broken_xorg_server(self):
        result = subprocess.run(['bash', str(GUARD)],
                                input=self.transaction(
                                    ('xserver-xorg-core', FIXED, BROKEN)),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('AMD graphics', result.stderr)

    def test_the_optin_config_never_names_the_broken_version(self):
        text = OPTIN_CONFIG.read_text(encoding='utf-8')
        self.assertNotIn(BROKEN, text)
        self.assertIn('xserver-xorg-core', PIN.read_text(encoding='utf-8'),
                      'the rollback package is not covered by the ABI pin')

    def test_the_xorg_abi_guard_tests_still_pass(self):
        env = dict(PATH='/usr/bin:/bin', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-m', 'unittest',
                                 'tests.test_xorg_abi_guard'],
                                cwd=str(ROOT), env=env, capture_output=True,
                                text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
