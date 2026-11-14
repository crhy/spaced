"""Issue #337: one bounded recovery pass for interrupted APT upgrades."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'


class UpdateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / 'bin'
        self.fakebin.mkdir()
        self.log = self.state / 'commands'
        self.guard = self.state / 'spaced-update-apt-guard'
        self.guard.write_text('#!/bin/bash\nexit 0\n')
        self.guard.chmod(0o755)
        # A dpkg database the cheap screen can read. It is healthy unless a test
        # breaks it: Spaced Update only runs the slow `dpkg --audit` when the
        # screen finds something (dpkg 1.23.12 reads one control file per
        # installed package, 7 s on the live image).
        self.admindir = self.state / 'dpkg'
        (self.admindir / 'info').mkdir(parents=True)
        (self.admindir / 'updates').mkdir()
        self.healthy_status = ('Package: spaced-meta\n'
                               'Status: install ok installed\n'
                               'Architecture: amd64\n\n')
        self.write_status(self.healthy_status)
        (self.admindir / 'info' / 'spaced-meta.list').write_text('/usr/bin/spaced\n')
        self.command('apt-get', r'''
printf 'apt-get %s\n' "$*" >> "$TEST_STATE/commands"
case " $* " in
  *" --simulate "*)
    if (( SIMULATE_STATUS != 0 )); then
        printf 'The following packages have unmet dependencies: perl\n'
    fi
    exit "$SIMULATE_STATUS" ;;
  *" --download-only "*) exit 0 ;;
esac
if [[ " $* " == *" dist-upgrade spaced-meta "* ]]; then
    count=$(cat "$TEST_STATE/install-count" 2>/dev/null || printf 0)
    count=$((count+1))
    printf '%s\n' "$count" > "$TEST_STATE/install-count"
    if (( count <= FAIL_INSTALLS )); then
        printf 'simulated package configuration failure\n'
        exit 42
    fi
fi
exit 0
''')
        self.command('dpkg', r'''
printf 'dpkg %s\n' "$*" >> "$TEST_STATE/commands"
if [[ $1 == --audit ]]; then
    count=$(cat "$TEST_STATE/audit-count" 2>/dev/null || printf 0)
    count=$((count+1))
    printf '%s\n' "$count" > "$TEST_STATE/audit-count"
    if (( count == AUDIT_FAILURE_AT )); then
        printf 'package is unpacked but not configured\n'
    fi
fi
''')
        self.command('apt-mark', 'exit 0')
        self.command('update-initramfs', 'exit 0')
        self.command('update-grub', 'exit 0')
        self.command('flatpak', 'exit 0')
        self.env = dict(os.environ,
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'],
                        TEST_STATE=str(self.state), FAIL_INSTALLS='1',
                        SIMULATE_STATUS='0', AUDIT_FAILURE_AT='0',
                        DPKG_ADMINDIR=str(self.admindir),
                        SPACED_UPDATE_TEST='1',
                        SPACED_UPDATE_TEST_GUARD=str(self.guard))

    def write_status(self, text):
        (self.admindir / 'status').write_text(text)

    def command(self, name, body):
        path = self.fakebin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)

    def run_helper(self, failures, simulation_status=0, audit_failure_at=0):
        if audit_failure_at:
            # The screen must notice the broken database, otherwise the full
            # audit (and with it the failure the test injects) never runs.
            self.write_status(self.healthy_status +
                              'Package: brokenpkg\n'
                              'Status: install ok half-installed\n'
                              'Architecture: amd64\n\n')
        env = dict(self.env, FAIL_INSTALLS=str(failures),
                   SIMULATE_STATUS=str(simulation_status),
                   AUDIT_FAILURE_AT=str(audit_failure_at))
        return subprocess.run(['bash', str(HELPER), 'all'], env=env,
                              capture_output=True, text=True, timeout=30)

    def lines(self, prefix):
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines()
                if line.startswith(prefix)]

    def test_failed_install_is_configured_and_retried_once(self):
        result = self.run_helper(1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('retrying pending package configuration once',
                      result.stdout)
        self.assertIn('SPACED_STEP:40:Recovering interrupted package configuration',
                      result.stdout)
        self.assertEqual((self.state / 'install-count').read_text(), '2\n')
        self.assertEqual(len(self.lines('dpkg --force-confdef')), 3)

    def test_second_failure_is_reported_without_an_unbounded_loop(self):
        result = self.run_helper(2)
        self.assertEqual(result.returncode, 42)
        self.assertEqual((self.state / 'install-count').read_text(), '2\n')
        self.assertIn('Update stopped (status 42)', result.stdout)

    def test_successful_install_is_not_retried(self):
        result = self.run_helper(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / 'install-count').read_text(), '1\n')
        self.assertNotIn('retrying pending package configuration once',
                         result.stdout)

    def test_failed_plan_explains_repository_transition_without_installing(self):
        result = self.run_helper(0, simulation_status=100)
        self.assertEqual(result.returncode, 100)
        self.assertIn('unmet dependencies: perl', result.stdout)
        self.assertIn('could not produce a safe upgrade plan', result.stdout)
        self.assertIn('Do not force the upgrade from a terminal', result.stdout)
        self.assertFalse((self.state / 'install-count').exists())
        self.assertFalse(any('--download-only' in line
                             for line in self.lines('apt-get ')))

    def test_unhealthy_database_is_refused_before_installing(self):
        result = self.run_helper(0, audit_failure_at=1)
        self.assertEqual(result.returncode, 1)
        self.assertIn('brokenpkg has the incomplete package state', result.stdout)
        self.assertIn('not healthy before the update', result.stdout)
        self.assertFalse((self.state / 'install-count').exists())

    def test_healthy_database_skips_the_slow_full_audit(self):
        # dpkg 1.23.12's audit opens one control file per installed package: on
        # the live image it costs 7.2 s per call, twice per transaction.
        result = self.run_helper(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.lines('dpkg --audit'), [])
        self.assertEqual((self.state / 'install-count').read_text(), '1\n')

    def test_missing_files_list_is_screened_and_audited(self):
        (self.admindir / 'info' / 'spaced-meta.list').unlink()
        result = self.run_helper(0)
        self.assertIn('spaced-meta has no files list in the package database',
                      result.stdout)
        self.assertIn('Running the full dpkg audit', result.stdout)
        self.assertEqual(len(self.lines('dpkg --audit')), 2)

    def test_unhealthy_database_after_install_is_reported(self):
        result = self.run_helper(0, audit_failure_at=2)
        self.assertEqual(result.returncode, 1)
        self.assertIn('not healthy after the update', result.stdout)
        self.assertEqual((self.state / 'install-count').read_text(), '1\n')

    def test_incomplete_database_directory_falls_back_to_the_audit(self):
        (self.admindir / 'updates').rmdir()
        result = self.run_helper(0)
        self.assertIn('is incomplete', result.stdout)
        self.assertEqual(len(self.lines('dpkg --audit')), 2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
