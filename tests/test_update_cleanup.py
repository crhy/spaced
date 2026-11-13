"""Issue #217: optional, confirmed Spaced Update cleanup action.

Runs overlays/usr/lib/spaced-linux/spaced-update-helper against fake
apt-get/uname/dpkg-query on PATH. No root access or real APT state needed:
SPACED_UPDATE_TEST=1 skips the system transaction lock (pkexec strips test
variables in production, so the hook cannot affect privileged runs) and
SPACED_UPDATE_TEST_CACHE_DIR points the helper at a scratch cache directory.
"""
import os
from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-update-helper'
RUNNING_KERNEL = '6.1.0-99-amd64'

try:
    _spec = importlib.util.spec_from_file_location(
        'spaced_update',
        ROOT / 'overlays/usr/lib/spaced-linux/spaced-update.py')
    spaced_update = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spaced_update)
except Exception:
    # GUI mapping tests are skipped where PyGObject/GTK is unavailable;
    # check.sh still asserts the GUI handles the cache-only status code.
    spaced_update = None

APT_GET = """#!/bin/bash
echo "$@" >> "$FAKE_APT_LOG"
if [[ " $* " == *" clean "* || "${!#}" == clean ]]; then
    find "$SPACED_UPDATE_TEST_CACHE_DIR" -type f ! -name lock -delete
fi
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
        # Stub APT transaction guard. It is owned by the invoking test user,
        # so the helper relaxes only the root-ownership check in test mode;
        # existence, executability, and no-group/other-write still apply.
        self.guard = self.state / 'spaced-update-apt-guard'
        self.guard.write_text('#!/bin/bash\nexit 0\n')
        self.guard.chmod(0o755)
        self.env = dict(os.environ,
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'],
                        SPACED_UPDATE_TEST='1',
                        SPACED_UPDATE_TEST_CACHE_DIR=str(self.cache),
                        SPACED_UPDATE_TEST_GUARD=str(self.guard),
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
        self.assertEqual(cache, 4096)
        self.assertFalse(any('Pre-Install-Pkgs' in invocation
                             for invocation in self.apt_invocations()),
                         self.apt_invocations())

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

    def test_apply_installs_transaction_guard(self):
        result = self.run_helper('cleanup-apply', 'libfoo1')
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = 'DPkg::Pre-Install-Pkgs::=%s' % self.guard
        self.assertTrue(any(expected in invocation
                            for invocation in self.apt_invocations()),
                        self.apt_invocations())

    def test_cache_only_cleanup_reclaims_reported_bytes(self):
        (self.cache / 'lock').write_bytes(b'lock metadata')
        partial = self.cache / 'partial'
        partial.mkdir()
        (partial / 'download.deb').write_bytes(b'x' * 1024)
        before = self.run_helper('cleanup-plan')
        self.assertEqual(self.plan_lines(before.stdout)[2], 5120)
        applied = self.run_helper('cleanup-apply')
        self.assertEqual(applied.returncode, 0, applied.stderr)
        after = self.run_helper('cleanup-plan')
        self.assertEqual(self.plan_lines(after.stdout)[2], 0)
        self.assertTrue((self.cache / 'lock').exists())

    def test_apply_with_blocked_plan_runs_only_clean(self):
        result = self.run_helper('cleanup-apply', 'mate-panel libfoo1')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('mate-panel', result.stdout)
        self.assertIn('Package cache cleaned', result.stdout)
        self.assertNotIn('Update stopped', result.stdout)
        invocations = self.apt_invocations()
        self.assertTrue(any('clean' in invocation.split()
                            for invocation in invocations),
                        invocations)
        self.assert_autoremove_never_applied()

    def test_apply_with_clean_plan_runs_clean_and_autoremove(self):
        result = self.run_helper('cleanup-apply', 'libfoo1 libbar2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Cleanup complete', result.stdout)
        invocations = self.apt_invocations()
        applied = [invocation for invocation in invocations
                   if '-y' in invocation.split()]
        self.assertTrue(any('clean' in invocation.split() for invocation in applied),
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


@unittest.skipUnless(spaced_update, 'PyGObject/GTK is unavailable')
class CleanupGuiMappingTests(unittest.TestCase):
    def test_exit_code_mapping(self):
        self.assertEqual(spaced_update.CLEANUP_CACHE_ONLY_STATUS, 3)
        self.assertEqual(spaced_update.cleanup_apply_outcome(0), 'done')
        self.assertEqual(spaced_update.cleanup_apply_outcome(3), 'cache-only')
        for status in (1, 2, 75, 126):
            self.assertEqual(spaced_update.cleanup_apply_outcome(status),
                             'failed', status)

    def test_blocked_package_parsing(self):
        output = ('Cleanup refused automatic removal for safety.\n'
                  'Blocked package: mate-panel (matches protected pattern mate-)\n'
                  'Blocked package: compiz-core (matches protected pattern compiz)\n'
                  'SPACED_STEP:40:Cleaning the package cache\n'
                  'Package cache cleaned.\n')
        self.assertEqual(spaced_update.App._parse_blocked_packages(output),
                         ['mate-panel', 'compiz-core'])
        self.assertEqual(spaced_update.App._parse_blocked_packages(''), [])
        self.assertEqual(spaced_update.App._parse_blocked_packages(None), [])


@unittest.skipUnless(spaced_update, 'PyGObject/GTK is unavailable')
class CleanupApplyResultTests(unittest.TestCase):
    """a01-updater rows 1 and 2: exactly one cleanup outcome is reported.

    App._cleanup_apply_done is driven with a fake app namespace and a stubbed
    Gtk.MessageDialog, so no window is realised and no display is needed.
    """

    def apply_done(self, succeeded, kind, message):
        built, statuses = [], []

        class RecordingDialog:
            def __init__(self, text=None, **kwargs):
                self.text = text
                self.secondary = None
                built.append(self)

            def format_secondary_text(self, text):
                self.secondary = text

            def connect(self, *args):
                pass

            def show_all(self):
                pass

        app = types.SimpleNamespace(
            _set_busy=lambda *args: None,
            _set_status=lambda icon, title, detail: statuses.append(
                (title, detail)),
            _parse_blocked_packages=spaced_update.App._parse_blocked_packages,
        )
        original = spaced_update.Gtk.MessageDialog
        try:
            spaced_update.Gtk.MessageDialog = RecordingDialog
            spaced_update.App._cleanup_apply_done(app, succeeded, kind, message)
        finally:
            spaced_update.Gtk.MessageDialog = original
        return built, statuses

    def test_cache_only_cleanup_never_claims_packages_were_removed(self):
        message = ('Cleanup refused automatic removal for safety; cleaning the '
                   'package cache only.\n'
                   'Blocked package: mate-panel (matches protected pattern mate-)\n'
                   'SPACED_STEP:40:Cleaning the package cache\n'
                   'Package cache cleaned.\n')
        built, statuses = self.apply_done(True, 'cache-only', message)
        self.assertEqual([dialog.text for dialog in built],
                         ['Package cache cleaned'])
        self.assertEqual([title for title, _ in statuses],
                         ['Package cache cleaned'])
        self.assertIn('mate-panel', built[0].secondary)

    def test_failed_cleanup_with_a_long_output_still_reports(self):
        built, statuses = self.apply_done(False, 'failed', 'dpkg error\n' * 400)
        self.assertEqual([dialog.text for dialog in built],
                         ['Cleanup did not complete'])
        self.assertEqual([title for title, _ in statuses],
                         ['Cleanup needs attention'])
        self.assertEqual(len(built[0].secondary), 3001)
        self.assertTrue(built[0].secondary.endswith('\u2026'))

    def test_full_cleanup_reports_packages_and_cache_removed(self):
        built, statuses = self.apply_done(True, 'done', 'Cleanup complete.')
        self.assertEqual([dialog.text for dialog in built], ['Cleanup complete'])
        self.assertEqual([title for title, _ in statuses], ['Cleanup complete'])


@unittest.skipUnless(spaced_update, 'PyGObject/GTK is unavailable')
class CleanupConfirmationTests(unittest.TestCase):
    """a01-updater row 5: the confirmation must match what can be cleaned."""

    def show_dialog(self, removes, blocked, cache_bytes):
        built = []

        class RecordingDialog:
            def __init__(self, text=None, **kwargs):
                self.text = text
                self.secondary = None
                self.buttons = []
                self.default = None
                built.append(self)

            def format_secondary_text(self, text):
                self.secondary = text

            def add_button(self, label, response):
                self.buttons.append((label, response))

            def set_default_response(self, response):
                self.default = response

            def connect(self, *args):
                pass

            def show_all(self):
                pass

        app = types.SimpleNamespace(
            _set_busy=lambda *args: None,
            _format_cleanup_bytes=spaced_update.App._format_cleanup_bytes,
            _on_cleanup_response=lambda *args: None,
        )
        original = spaced_update.Gtk.MessageDialog
        try:
            spaced_update.Gtk.MessageDialog = RecordingDialog
            spaced_update.App._show_cleanup_dialog(
                app, removes, blocked, cache_bytes)
        finally:
            spaced_update.Gtk.MessageDialog = original
        return built

    def test_cache_only_confirmation_offers_only_the_cache(self):
        # The ordinary state after any install: nothing is autoremoveable,
        # but /var/cache/apt/archives still holds downloads.
        dialog = self.show_dialog([], [], 4096)[0]
        self.assertEqual(dialog.text, 'Clean the package cache?')
        self.assertNotIn('These unused packages will be removed',
                         dialog.secondary)
        self.assertIn('4.0 KB', dialog.secondary)
        self.assertIn(("Clean Package Cache", spaced_update.Gtk.ResponseType.APPLY),
                      dialog.buttons)

    def test_removal_confirmation_still_lists_the_packages(self):
        dialog = self.show_dialog([('libfoo1', '1.2.3')], [], 4096)[0]
        self.assertEqual(dialog.text, 'Clean up unused packages?')
        self.assertIn('These unused packages will be removed:', dialog.secondary)
        self.assertIn('libfoo1 (1.2.3)', dialog.secondary)
        self.assertIn(('Clean Up', spaced_update.Gtk.ResponseType.OK),
                      dialog.buttons)


@unittest.skipUnless(spaced_update, 'PyGObject/GTK is unavailable')
class InstallWarningTests(unittest.TestCase):
    """a01-updater row 6: SPACED_WARNING lines must reach the user."""

    def test_selected_install_reports_helper_warnings(self):
        statuses, logged, calls = [], [], []
        app = types.SimpleNamespace(
            _update_warnings=[],
            setstep=lambda *args: None,
            logline=lambda line: logged.append(line),
            show_error=lambda *args: None,
            back_button=types.SimpleNamespace(show=lambda: None),
            _set_busy=lambda *args: None,
            _set_status=lambda icon, title, detail: statuses.append(
                (title, detail)),
        )

        def run_cmd(command, *args):
            calls.append(command)
            # run_cmd() collects each SPACED_WARNING: line from the helper.
            app._update_warnings.append('mate-panel is held by the administrator')
            return 0
        app.run_cmd = run_cmd
        original = spaced_update.GLib.idle_add
        try:
            spaced_update.GLib.idle_add = lambda function, *args: function(*args)
            spaced_update.App._install_worker(
                app, [{'kind': 'apt', 'name': 'mate-panel', 'package': 'mate-panel'}])
        finally:
            spaced_update.GLib.idle_add = original
        self.assertEqual(calls, [['pkexec', spaced_update.HELPER, 'apt-install',
                                  'mate-panel']])
        self.assertEqual([title for title, _ in statuses][-1],
                         'Update finished with warnings')
        self.assertIn('held by the administrator', statuses[-1][1])
        self.assertIn('mate-panel is held by the administrator', logged)


if __name__ == '__main__':
    unittest.main()
