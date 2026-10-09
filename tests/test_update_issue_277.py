"""Issue #277: password-free checking, real APT progress, in-app release notes."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'overlays/usr/lib/spaced-linux'
REFRESH = LIB / 'spaced-update-refresh'
HELPER = LIB / 'spaced-update-helper'
POLICY = ROOT / 'overlays/usr/share/polkit-1/actions/com.spacedlinux.update.policy'
sys.dont_write_bytecode = True

try:
    _spec = importlib.util.spec_from_file_location(
        'spaced_update_277', LIB / 'spaced-update.py')
    spaced_update = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(spaced_update)
except Exception:
    spaced_update = None

APT_GET = """#!/bin/bash
printf '%s\\n' "$*" >> "$FAKE_APT_LOG"
exit 0
"""


class PolicyTests(unittest.TestCase):
    def test_only_the_refresh_action_skips_the_password(self):
        actions = {a.attrib['id']: a for a in ET.parse(POLICY).getroot().findall('action')}
        self.assertEqual(set(actions),
                         {'com.spacedlinux.update', 'com.spacedlinux.update.refresh'})
        for action_id, action in actions.items():
            defaults = action.find('defaults')
            self.assertEqual(defaults.findtext('allow_any'), 'auth_admin')
            self.assertEqual(defaults.findtext('allow_inactive'), 'auth_admin')
            refresh = action_id.endswith('.refresh')
            self.assertEqual(defaults.findtext('allow_active') == 'yes', refresh)
            self.assertEqual(action.find('annotate').text,
                             str(Path('/usr/lib/spaced-linux') / (REFRESH if refresh else HELPER).name))


class RefreshHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        state = Path(self.temp.name)
        (state / 'bin').mkdir()
        (state / 'bin/apt-get').write_text(APT_GET)
        (state / 'bin/apt-get').chmod(0o755)
        self.log = state / 'apt.log'
        # The real lock lives in /run/lock, which a test user may not own.
        self.script = state / 'spaced-update-refresh'
        self.script.write_text(REFRESH.read_text().replace(
            '/run/lock/spaced-update.lock', str(state / 'lock')))
        self.env = dict(os.environ, FAKE_APT_LOG=str(self.log),
                        PATH=str(state / 'bin') + os.pathsep + os.environ['PATH'])

    def run_refresh(self, *args):
        return subprocess.run(['bash', str(self.script), *args], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_is_executable(self):
        self.assertTrue(os.access(REFRESH, os.X_OK))

    def test_rejects_every_argument(self):
        for args in (('apt-install', 'evil'), ('all',), ('update',), ('-o', 'x=y')):
            with self.subTest(args=args):
                result = self.run_refresh(*args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_only_refreshes_package_lists(self):
        result = self.run_refresh()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith(' update'))
        self.assertIn('SPACED_STEP:100:Package lists refreshed', result.stdout)


class HelperProgressTests(unittest.TestCase):
    def test_progress_filter_keeps_ordinary_apt_output(self):
        # The log in the Details pane is the only record of a failed upgrade.
        text = HELPER.read_text()
        start = text.index("sed -u -e '") + len("sed -u -e '")
        expression = text[start:text.index("'", start)]
        result = subprocess.run(
            ['sed', '-e', expression], capture_output=True, text=True,
            input='Setting up brave (1.0) ...\npmstatus:brave:50.0:Installing brave (amd64)\n'
                  'dlstatus:1:10.0:Retrieving file 1 of 3\n')
        self.assertEqual(result.stdout.splitlines(), [
            'Setting up brave (1.0) ...',
            'STATUS pmstatus:brave:50.0:Installing brave (amd64)',
            'STATUS dlstatus:1:10.0:Retrieving file 1 of 3'])


@unittest.skipIf(spaced_update is None, 'needs PyGObject/GTK')
class AppTests(unittest.TestCase):
    def test_check_uses_the_password_free_helper(self):
        source = (LIB / 'spaced-update.py').read_text()
        self.assertIn('run_capture(["pkexec", REFRESH_HELPER]', source)
        self.assertNotIn('HELPER, "apt-refresh"', source)
        self.assertEqual(spaced_update.REFRESH_HELPER, '/usr/lib/spaced-linux/' + REFRESH.name)

    def test_apt_status_lines_become_progress(self):
        parse = spaced_update.parse_apt_status
        self.assertEqual(parse('dlstatus:1:25.5:Retrieving file 2 of 8'), (25.5, 'Downloading 2 of 8'))
        self.assertEqual(parse('pmstatus:brave:150:Installing brave (amd64)'), (100.0, 'Installing brave'))
        self.assertIsNone(parse('Setting up brave (1.0) ...'))

    def test_release_notes_render_or_fall_back_to_plain_text(self):
        to_markup = spaced_update.notes_to_markup
        markup = to_markup('## 10.26.2\n### Fixes\n- **Bold** and `code` <tag> [link](https://x.y/z)\n')
        spaced_update.Pango.parse_markup(markup, -1, '\0')
        self.assertIn('<b>Bold</b>', markup)
        self.assertIn('&lt;tag&gt;', markup)
        self.assertNotIn('#', markup)
        # Overlapping bold and code spans are not valid Pango markup; the
        # dialog must show the text instead of an empty label.
        broken = '- **bold `code** tail`'
        self.assertEqual(to_markup(broken), spaced_update.GLib.markup_escape_text(broken))


if __name__ == '__main__':
    unittest.main()
