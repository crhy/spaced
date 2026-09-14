"""Issue #217: optional, confirmed Spaced Update cleanup action.

Runs overlays/usr/lib/spaced-linux/spaced-update-helper against fake
apt-get/uname/dpkg-query on PATH. No root access or real APT state needed:
SPACED_UPDATE_TEST=1 skips the system transaction lock (pkexec strips test
variables in production, so the hook cannot affect privileged runs) and
SPACED_UPDATE_TEST_CACHE_DIR points du at a scratch cache directory.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'
RUNNING_KERNEL = '6.1.0-99-amd64'

APT_GET = """#!/bin/bash
echo "$@" >> "$FAKE_APT_LOG"
if [[ " $* " == *" -s "* && " $* " == *" autoremove"* ]]; then
    printf 'Reading package lists... Done\\n'
    printf 'Building dependency tree... Done\\n'
    printf 'The following packages will be REMOVED:\\n'
    if [[ -n "${FAKE_APT_REMOVE:-}" ]]; then
        # shellcheck disable=SC2086
        printf '  %s\\n' ${FAKE_APT_REMOVE}
    fi
    printf '0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\\n'
fi
exit 0
"""

UNAME = ("#!/bin/bash\n"
         "if [[ \"${1:-}\" == -r ]]; then\n"
         "    printf '%s\\n' \"${FAKE_UNAME_R:-" + RUNNING_KERNEL + "}\"\n"
         "    exit 0\n"
         "fi\n"
         "exit 0\n")

DPKG_QUERY = """#!/bin/bash
printf '1.2.3-test\\n'
exit 0
"""


class CleanupHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fakebin = self.state / 'bin'
        self.fakebin.mkdir()
        self.cache = self.state / 'archives'
        self.cache.mkdir()
        (self.cache / 'stale_1.0_amd64.deb').write_bytes(b'x' * 4096)
        self.log = self.state / 'apt.log'
        (self.fakebin / 'apt-get').write_text(APT_GET)
        (self.fakebin / 'uname').write_text(UNAME)
        (self.fakebin / 'dpkg-query').write_text(DPKG_QUERY)
        for name in ('apt-get', 'uname', 'dpkg-query'):
            (self.fakebin / name).chmod(0o755)
        self.env = dict(os.environ,
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'],
                        SPACED_UPDATE_TEST='1',
                        SPACED_UPDATE_TEST_CACHE_DIR=str(self.cache),
                        FAKE_APT_LOG=str(self.log),
                        FAKE_UNAME_R=RUNNING_KERNEL)

    def run_helper(self, mode, remove=''):
        env = dict(self.env, FAKE_APT_REMOVE=remove)
        return subprocess.run(['bash', str(HELPER), mode], env=env,
                              capture_output=True, text=True, timeout=30)

    @staticmethod
    def plan_lines(output):
        removes, blocked, cache = [], [], None
        for line in output.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[0] == 'REMOVE':
                removes.append((parts[1], parts[2]))
            elif len(parts) == 3 and parts[0] == 'BLOCKED':
                blocked.append((parts[1], parts[2]))
            elif len(parts) == 2 and parts[0] == 'AUTOCLEAN_BYTES':
                cache = int(parts[1])
        return removes, blocked, cache

    def apt_invocations(self):
        if not self.log.exists():
            return []
        return self.log.read_text().splitlines()

    def assert_autoremove_never_applied(self):
        for invocation in self.apt_invocations():
            if 'autoremove' in invocation:
                words = invocation.split()
                self.assertIn('-s', words, invocation)
                self.assertNotIn('-y', words, invocation)

    def test_plan_lists_safe_removals(self):
        result = self.run_helper('cleanup-plan', 'libfoo1 libbar2')
        self.assertEqual(result.returncode, 0, result.stderr)
        removes, blocked, cache = self.plan_lines(result.stdout)
        self.assertEqual(removes, [('libfoo1', '1.2.3-test'),
                                  ('libbar2', '1.2.3-test')])
        self.assertEqual(blocked, [])
        self.assertGreaterEqual(cache, 4096)

    def test_plan_marks_protected_desktop_packages_blocked(self):
        result = self.run_helper('cleanup-plan',
                                 'mate-panel compiz-core libinnocent')
        self.assertEqual(result.returncode, 0, result.stderr)
        removes, blocked, _ = self.plan_lines(result.stdout)
        self.assertEqual(removes, [('libinnocent', '1.2.3-test')])
        self.assertEqual([name for name, _ in blocked],
                         ['mate-panel', 'compiz-core'])

    def test_plan_marks_spaced_meta_blocked(self):
        result = self.run_helper('cleanup-plan', 'spaced-meta libfoo1')
        self.assertEqual(result.returncode, 0, result.stderr)
        removes, blocked, _ = self.plan_lines(result.stdout)
        self.assertEqual(removes, [('libfoo1', '1.2.3-test')])
        self.assertEqual([name for name, _ in blocked], ['spaced-meta'])

    def test_plan_marks_running_kernel_blocked_but_not_older_kernel(self):
        result = self.run_helper(
            'cleanup-plan',
            'linux-image-%s linux-headers-%s linux-image-6.1.0-98-amd64'
            % (RUNNING_KERNEL, RUNNING_KERNEL))
        self.assertEqual(result.returncode, 0, result.stderr)
        removes, blocked, _ = self.plan_lines(result.stdout)
        self.assertEqual(removes, [('linux-image-6.1.0-98-amd64', '1.2.3-test')])
        self.assertEqual([name for name, _ in blocked],
                         ['linux-image-' + RUNNING_KERNEL,
                          'linux-headers-' + RUNNING_KERNEL])

    def test_plan_refuses_unusually_large_removal_set(self):
        packages = ' '.join('stale-pkg%02d' % number for number in range(55))
        result = self.run_helper('cleanup-plan', packages)
        self.assertEqual(result.returncode, 0, result.stderr)
        removes, blocked, _ = self.plan_lines(result.stdout)
        self.assertEqual(removes, [])
        self.assertEqual(len(blocked), 55)
        for _, reason in blocked:
            self.assertIn('unusually large removal set; refusing', reason)

    def test_plan_reports_empty_cleanup(self):
        result = self.run_helper('cleanup-plan', '')
        self.assertEqual(result.returncode, 0, result.stderr)
        removes, blocked, cache = self.plan_lines(result.stdout)
        self.assertEqual(removes, [])
        self.assertEqual(blocked, [])
        self.assertIsNotNone(cache)

    def test_apply_with_blocked_plan_runs_only_autoclean(self):
        result = self.run_helper('cleanup-apply', 'mate-panel libfoo1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('mate-panel', result.stdout)
        invocations = self.apt_invocations()
        self.assertTrue(any('autoclean' in invocation
                            for invocation in invocations),
                        invocations)
        self.assert_autoremove_never_applied()

    def test_apply_with_clean_plan_runs_autoclean_and_autoremove(self):
        result = self.run_helper('cleanup-apply', 'libfoo1 libbar2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Cleanup complete', result.stdout)
        invocations = self.apt_invocations()
        applied = [invocation for invocation in invocations
                   if '-y' in invocation.split()]
        self.assertTrue(any('autoclean' in invocation for invocation in applied),
                        applied)
        self.assertTrue(any('autoremove' in invocation for invocation in applied),
                        applied)

    def test_update_path_never_cleans_up_automatically(self):
        helper = HELPER.read_text(encoding='utf-8')
        update_path = helper.split(
            'TRANSACTION=(dist-upgrade', 1)[1].split(
                'Requested system updates complete', 1)[0]
        self.assertNotIn('autoremove', update_path)
        self.assertNotIn('autoclean', update_path)


if __name__ == '__main__':
    unittest.main()
