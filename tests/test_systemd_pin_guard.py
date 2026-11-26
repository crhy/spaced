"""Audit row a08-13: the anti-systemd pin and the APT transaction guard cover
the whole systemd-* family, except the sysusers and tmpfiles providers the
image installs (config/packages.yaml)."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-apt-guard'
PIN = ROOT / 'overlays/etc/apt/preferences.d/spaced-init'
PROVIDERS = ('systemd-standalone-sysusers', 'systemd-standalone-tmpfiles')
UNIT_PACKAGES = ('systemd-container', 'systemd-oomd', 'systemd-coredump',
                 'systemd-socket-activate', 'systemd-timers')


def transaction(*actions):
    return 'VERSION 2\nAPT::Architecture=amd64\n\n' + ''.join(
        f'{package} {old} < {new} /var/cache/apt/archives/{package}.deb\n'
        for package, old, new in actions)


def removal(*packages):
    return 'VERSION 2\nAPT::Architecture=amd64\n\n' + ''.join(
        f'{package} 1.0 = 1.0 **REMOVE**\n' for package in packages)


def stanzas(text):
    blocks = []
    for block in text.strip().split('\n\n'):
        fields = {}
        for line in block.splitlines():
            key, separator, value = line.partition(':')
            if separator:
                fields[key.strip()] = value.strip()
        blocks.append(fields)
    return blocks


class GuardTests(unittest.TestCase):
    def run_guard(self, text):
        return subprocess.run(['bash', str(GUARD)], input=text,
                              capture_output=True, text=True, timeout=10)

    def test_systemd_unit_packages_are_refused(self):
        for package in UNIT_PACKAGES:
            result = self.run_guard(transaction((package, '0', '1.0')))
            self.assertEqual(result.returncode, 1, f'{package} was accepted')
            self.assertIn('sysvinit system', result.stderr)

    def test_plain_systemd_is_still_refused(self):
        for package in ('systemd', 'systemd-sysv'):
            result = self.run_guard(transaction((package, '0', '1.0')))
            self.assertEqual(result.returncode, 1, f'{package} was accepted')
            self.assertIn('sysvinit system', result.stderr)

    def test_other_init_systems_are_still_refused(self):
        for package in ('runit-init', 'openrc'):
            result = self.run_guard(transaction((package, '0', '1.0')))
            self.assertEqual(result.returncode, 1, f'{package} was accepted')
            self.assertIn('sysvinit system', result.stderr)

    def test_sysvinit_removal_is_still_refused(self):
        result = self.run_guard(removal('sysvinit-core'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('core Spaced Linux package', result.stderr)

    def test_sysusers_and_tmpfiles_providers_are_allowed(self):
        result = self.run_guard(transaction(
            (PROVIDERS[0], '0', '1.0'), (PROVIDERS[1], '0', '1.0')))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_provider_upgrade_is_allowed_next_to_a_normal_upgrade(self):
        result = self.run_guard(transaction(
            ('sysvinit-core', '1.0', '2.0'), (PROVIDERS[0], '1.0', '2.0')))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_removing_a_systemd_unit_package_is_allowed(self):
        # Taking systemd-* out of the system is the desired direction, so the
        # wildcard must not refuse a removal.
        result = self.run_guard(removal('systemd-container'))
        self.assertEqual(result.returncode, 0, result.stderr)


class PinTests(unittest.TestCase):
    def test_wildcard_stanza_blocks_the_systemd_family(self):
        blocked = [stanza for stanza in stanzas(PIN.read_text())
                   if stanza.get('Package') == 'systemd systemd-*']
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].get('Pin'), 'version *')
        self.assertEqual(blocked[0].get('Pin-Priority'), '-1')

    def test_provider_stanza_keeps_the_sysusers_and_tmpfiles_installable(self):
        exempt = [stanza for stanza in stanzas(PIN.read_text())
                  if set(stanza.get('Package', '').split()) == set(PROVIDERS)]
        self.assertEqual(len(exempt), 1)
        self.assertEqual(exempt[0].get('Pin'), 'version *')
        self.assertGreater(int(exempt[0].get('Pin-Priority')), 0)

    def test_provider_stanza_comes_first_because_apt_takes_the_first_match(self):
        # APT does not merge matching stanzas: the first stanza that matches a
        # package decides its priority, so a later wildcard could not be
        # overridden by an earlier-named exemption.
        text = PIN.read_text()
        self.assertLess(text.index('systemd-standalone-sysusers'),
                        text.index('Package: systemd systemd-*'))

    @unittest.skipUnless(shutil.which('apt-cache'), 'requires apt-cache')
    def test_pin_is_accepted_by_apt_and_keeps_the_providers_resolvable(self):
        with tempfile.TemporaryDirectory() as temp:
            shutil.copy(PIN, temp)
            result = subprocess.run(
                ['apt-cache', '-o', f'Dir::Etc::PreferencesParts={temp}',
                 'policy', PROVIDERS[0]],
                capture_output=True, text=True, timeout=60)
        self.assertNotIn('E:', result.stderr)
        if 'Version table:' not in result.stdout or '***' not in result.stdout:
            self.skipTest(f'{PROVIDERS[0]} is not in this host\'s package index')
        self.assertNotIn('Candidate: (none)', result.stdout)


if __name__ == '__main__':
    unittest.main()
