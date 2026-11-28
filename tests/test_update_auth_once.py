"""crhy/spacedupdate#19: a full update run authenticates exactly once.

The GUI collects the whole plan and runs ONE `pkexec spaced-update-helper
run-plan` whose stdin lists the allow-listed sub-steps. The root helper
validates every step before running any, then runs them in order and streams
the usual SPACED_STEP: lines. A fake pkexec on PATH counts the calls and
REALLY executes the helper (with a fake apt-get/flatpak on PATH), and a fake
sudo that fails the test if it is ever called. No real pkexec, polkit, sudo,
apt or flatpak runs here.
"""
from pathlib import Path
import importlib.util
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

try:
    _spec = importlib.util.spec_from_file_location(
        'spaced_update_auth_once',
        ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py')
    spaced_update = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spaced_update)
except Exception:
    spaced_update = None

HELPER_PATH = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'

PKEXEC = """#!/bin/bash
printf 'pkexec\\t%s\\n' "$*" >> "$UPDATE_LOG"
if [[ -n ${PKEXEC_EXIT:-} ]]; then exit "$PKEXEC_EXIT"; fi
exec "$@"
"""
SUDO = """#!/bin/bash
printf 'sudo\\t%s\\n' "$*" >> "$UPDATE_LOG"
echo "FAKE SUDO WAS CALLED: $*" >> "$UPDATE_LOG"
exit 1
"""
APT_GET = """#!/bin/bash
printf '%s\\n' "$*" >> "$APT_LOG"
exit ${APT_EXIT:-0}
"""
FLATPAK = """#!/bin/bash
printf '%s\\n' "$*" >> "$FLATPAK_LOG"
exit ${FLATPAK_EXIT:-0}
"""


class _FakeBin:
    """A PATH of fake pkexec/sudo/apt-get/flatpak plus the logs they write."""

    def __init__(self, temp):
        base = Path(temp)
        self.bin = base / 'bin'
        self.bin.mkdir(exist_ok=True)
        self.update_log = base / 'update.log'
        self.apt_log = base / 'apt.log'
        self.flatpak_log = base / 'flatpak.log'
        for name, text in (('pkexec', PKEXEC), ('sudo', SUDO),
                          ('apt-get', APT_GET), ('flatpak', FLATPAK)):
            script = self.bin / name
            script.write_text(text)
            script.chmod(script.stat().st_mode | stat.S_IEXEC)
        for log in (self.update_log, self.apt_log, self.flatpak_log):
            log.write_text('')

    def env(self, **overrides):
        env = dict(os.environ)
        env['PATH'] = f'{self.bin}{os.pathsep}{os.environ["PATH"]}'
        env['UPDATE_LOG'] = str(self.update_log)
        env['APT_LOG'] = str(self.apt_log)
        env['FLATPAK_LOG'] = str(self.flatpak_log)
        env['SPACED_UPDATE_TEST'] = '1'
        env['SPACED_UPDATE_TEST_CACHE_DIR'] = str(self.apt_log.parent / 'cache')
        env.update({k: str(v) for k, v in overrides.items()})
        return env

    def rows(self, log):
        return [line.split('\t') for line in log.read_text().splitlines() if line]

    def pkexec_calls(self):
        return [r for r in self.rows(self.update_log) if r and r[0] == 'pkexec']

    def sudo_calls(self):
        return [r for r in self.rows(self.update_log) if r and r[0] == 'sudo']

    def run_helper(self, argv, env, stdin=''):
        return subprocess.run(['bash', str(HELPER_PATH), *argv], env=env,
                              input=stdin, capture_output=True, text=True, timeout=60)


@unittest.skipIf(spaced_update is None, 'needs PyGObject/GTK')
class RunPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fake = _FakeBin(self.temp.name)

    def test_full_run_is_one_pkexec_and_never_sudo(self):
        # The GUI's whole privileged run: one pkexec of run-plan whose stdin
        # lists the steps; the fake pkexec really runs the helper, which runs
        # each step and reaches the fake apt-get/flatpak. No sudo anywhere.
        plan = ('apt-refresh\n'
                'flatpak-update --system app/org.gnome.Maps/x86_64/stable\n'
                'cleanup-plan\n')
        result = subprocess.run(
            ['pkexec', str(HELPER_PATH), 'run-plan'], env=self.fake.env(),
            input=plan, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.fake.pkexec_calls()), 1)
        self.assertEqual(self.fake.pkexec_calls()[0][1],
                         f'{HELPER_PATH} run-plan')
        self.assertEqual(self.fake.sudo_calls(), [])
        # The helper really executed the steps: apt update, the flatpak update
        # and the read-only cleanup plan each reached the fake binaries.
        self.assertTrue(any('update' in line
                            for line in self.fake.apt_log.read_text().splitlines()))
        self.assertIn('org.gnome.Maps', self.fake.flatpak_log.read_text())

    def test_module_run_plan_uses_exactly_one_pkexec(self):
        plan = [['apt-install', 'apt'], ['flatpak-update', '--system',
                                        'app/org.gnome.Maps/x86_64/stable']]
        seen = {}

        def invoker(command, plan_text):
            seen['command'] = command
            seen['plan'] = plan_text
            return 0

        spaced_update.run_plan(plan, invoker)
        self.assertEqual(seen['command'], ['pkexec', spaced_update.HELPER, 'run-plan'])
        self.assertEqual(
            seen['plan'],
            'apt-install apt\nflatpak-update --system app/org.gnome.Maps/x86_64/stable\n')

    def test_cancelled_pkexec_is_cleanly_not_authorised(self):
        # A cancelled pkexec (126) never executes the helper, and check_status
        # turns it into UpdateCancelled at the caller (issue #277 path reused).
        plan = 'apt-refresh\n'
        result = subprocess.run(
            ['pkexec', str(HELPER_PATH), 'run-plan'],
            env=self.fake.env(PKEXEC_EXIT=126),
            input=plan, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 126)
        self.assertEqual(self.fake.apt_log.read_text(), '')
        with self.assertRaises(spaced_update.UpdateCancelled):
            spaced_update.check_status(result.returncode)

    def test_unknown_step_is_rejected_before_anything_runs(self):
        # The plan mixes a valid step and an unknown one. The helper validates
        # every step first, so NOTHING runs and no side effect happens.
        plan = 'apt-refresh\nfrobnicate\n'
        result = self.fake.run_helper(['run-plan'], self.fake.env(), stdin=plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unknown update mode', result.stdout + result.stderr)
        self.assertEqual(self.fake.apt_log.read_text(), '')
        self.assertEqual(self.fake.flatpak_log.read_text(), '')

    def test_invalid_flatpak_ref_is_rejected_before_anything_runs(self):
        plan = 'flatpak-update --system app/../../etc/passwd\napt-refresh\n'
        result = self.fake.run_helper(['run-plan'], self.fake.env(), stdin=plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fake.flatpak_log.read_text(), '')
        self.assertEqual(self.fake.apt_log.read_text(), '')

    def test_failing_middle_step_skips_later_steps_and_reports(self):
        # apt-refresh fails (fake apt-get exits 1); the later flatpak step must
        # be skipped and the helper must say which step failed.
        plan = ('apt-refresh\n'
                'flatpak-update --system app/org.gnome.Maps/x86_64/stable\n')
        result = self.fake.run_helper(['run-plan'], self.fake.env(APT_EXIT=1),
                                      stdin=plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fake.flatpak_log.read_text(), '')
        self.assertIn('SPACED_PLAN_STOP', result.stdout)
        self.assertIn('apt-refresh', result.stdout)
        # The first step did reach the fake apt-get before it failed.
        self.assertIn('update', self.fake.apt_log.read_text())


@unittest.skipIf(spaced_update is None, 'needs PyGObject/GTK')
class PlanFileGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fake = _FakeBin(self.temp.name)

    def test_world_writable_plan_file_is_refused(self):
        plan = Path(self.temp.name) / 'plan'
        plan.write_text('apt-refresh\n')
        plan.chmod(0o666)
        result = self.fake.run_helper(['run-plan', '--plan', str(plan)],
                                      self.fake.env())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('writable by other accounts', result.stdout + result.stderr)
        self.assertEqual(self.fake.apt_log.read_text(), '')

    def test_non_root_owned_plan_file_is_refused(self):
        # Outside test mode the helper demands a root-owned plan file; a plan
        # written by the invoking user (not world-writable) is refused.
        plan = Path(self.temp.name) / 'plan'
        plan.write_text('apt-refresh\n')
        plan.chmod(0o600)
        env = self.fake.env()
        env.pop('SPACED_UPDATE_TEST')
        result = self.fake.run_helper(['run-plan', '--plan', str(plan)], env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not owned by root', result.stdout + result.stderr)
        self.assertEqual(self.fake.apt_log.read_text(), '')


if __name__ == '__main__':
    unittest.main()
