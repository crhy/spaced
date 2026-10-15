"""Issue #305: confirm every Compiz screenshot with a notification."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/usr/local/bin/spaced-screenshot-notify'


class ScreenshotNotifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls'
        self.log.touch()
        self.desktop = self.root / 'Desktop'
        self.desktop.mkdir()
        self.env = dict(PATH=str(self.bin), CALL_LOG=str(self.log),
                        DESKTOP_DIR=str(self.desktop))

    def fake(self, name, body, mode=0o755):
        script = self.bin / name
        script.write_text(body)
        script.chmod(mode)
        return script

    def log_call(self, name):
        return (
            "#!/bin/bash\n"
            "{ printf '" + name + "'; for a in \"$@\"; do printf '\\t%s' \"$a\"; done; "
            "printf '\\n'; } >> \"$CALL_LOG\"\n"
        )

    def invoke(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env,
                              capture_output=True, text=True, timeout=5)

    def calls(self):
        lines = self.log.read_text().splitlines()
        return [line.split('\t') for line in lines if line]

    def wait_for(self, name):
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if any(entry and entry[0] == name for entry in self.calls()):
                return True
            time.sleep(0.02)
        return any(entry and entry[0] == name for entry in self.calls())

    def test_explicit_path_notifies_with_basename(self):
        self.fake('notify-send', self.log_call('notify-send'))
        self.fake('xdg-user-dir',
                  self.log_call('xdg-user-dir') + 'printf \'%s\\n\' "$DESKTOP_DIR"\n')
        self.fake('canberra-gtk-play', self.log_call('canberra-gtk-play'))
        self.fake('basename', '#!/bin/bash\nprintf \'%s\\n\' "${1##*/}"\n')
        shot = self.desktop / 'capture.png'
        shot.touch()
        result = self.invoke(str(shot))
        self.assertEqual(result.returncode, 0)
        notify = [entry for entry in self.calls() if entry and entry[0] == 'notify-send']
        self.assertEqual(len(notify), 1)
        self.assertEqual(notify[0],
                         ['notify-send', '--app-name=Screenshot',
                          '--icon=' + str(shot), 'Screenshot saved', 'capture.png'])
        self.assertTrue(self.wait_for('canberra-gtk-play'))

    def test_newest_png_is_the_fallback(self):
        self.fake('notify-send', self.log_call('notify-send'))
        self.fake('xdg-user-dir',
                  self.log_call('xdg-user-dir') + 'printf \'%s\\n\' "$DESKTOP_DIR"\n')
        self.fake('canberra-gtk-play', self.log_call('canberra-gtk-play'))
        self.fake('basename', '#!/bin/bash\nprintf \'%s\\n\' "${1##*/}"\n')
        older = self.desktop / 'older.png'
        newer = self.desktop / 'newer.png'
        older.touch()
        newer.touch()
        os.utime(older, (1000, 1000))
        os.utime(newer, (2000, 2000))
        result = self.invoke('/does/not/exist.png')
        self.assertEqual(result.returncode, 0)
        notify = [entry for entry in self.calls() if entry and entry[0] == 'notify-send']
        self.assertEqual(len(notify), 1)
        self.assertEqual(notify[0],
                         ['notify-send', '--app-name=Screenshot',
                          '--icon=' + str(newer), 'Screenshot saved', 'newer.png'])
        self.assertTrue(self.wait_for('canberra-gtk-play'))

    def test_empty_desktop_calls_nothing(self):
        self.fake('notify-send', self.log_call('notify-send'))
        self.fake('xdg-user-dir',
                  self.log_call('xdg-user-dir') + 'printf \'%s\\n\' "$DESKTOP_DIR"\n')
        self.fake('canberra-gtk-play', self.log_call('canberra-gtk-play'))
        self.fake('basename', '#!/bin/bash\nprintf \'%s\\n\' "${1##*/}"\n')
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        names = [entry[0] for entry in self.calls() if entry]
        self.assertNotIn('notify-send', names)
        self.assertNotIn('canberra-gtk-play', names)

    def test_missing_notify_send_still_exits_zero(self):
        self.fake('xdg-user-dir',
                  self.log_call('xdg-user-dir') + 'printf \'%s\\n\' "$DESKTOP_DIR"\n')
        self.fake('canberra-gtk-play', self.log_call('canberra-gtk-play'))
        self.fake('basename', '#!/bin/bash\nprintf \'%s\\n\' "${1##*/}"\n')
        shot = self.desktop / 'shot.png'
        shot.touch()
        result = self.invoke(str(shot))
        self.assertEqual(result.returncode, 0)
        names = [entry[0] for entry in self.calls() if entry]
        self.assertNotIn('notify-send', names)


if __name__ == '__main__':
    unittest.main()
