"""Issue #297: guests must be able to reach folders shared from a home."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'overlays/usr/lib/spaced-linux/spaced-home-traverse'


class HomeTraverseTests(unittest.TestCase):
    def test_only_private_desktop_homes_open_to_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            homes = temp / 'home'
            modes = {'rhy': 0o700, 'alice': 0o750, 'svc': 0o700, 'locked': 0o700}
            for name, mode in modes.items():
                (homes / name).mkdir(parents=True)
                (homes / name).chmod(mode)
            outside = temp / 'srv'
            outside.mkdir()
            outside.chmod(0o700)
            bin_dir = temp / 'bin'
            bin_dir.mkdir()
            (bin_dir / 'getent').write_text(f'''#!/bin/sh
cat <<END
root:x:0:0::/root:/bin/bash
svc:x:998:998::{homes}/svc:/bin/sh
rhy:x:1000:1000::{homes}/rhy:/bin/bash
alice:x:1001:1001::{homes}/alice:/bin/bash
locked:x:1002:1002::{homes}/locked:/usr/sbin/nologin
other:x:1003:1003::{outside}:/bin/bash
END
''')
            (bin_dir / 'getent').chmod(0o755)
            env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}',
                       SPACED_HOME_ROOT=str(homes))
            for _ in range(2):
                subprocess.run(['bash', str(SCRIPT)], env=env, check=True,
                               capture_output=True)
            mode = lambda path: path.stat().st_mode & 0o777
            self.assertEqual(mode(homes / 'rhy'), 0o711)
            self.assertEqual(mode(homes / 'alice'), 0o750)
            self.assertEqual(mode(homes / 'svc'), 0o700)
            self.assertEqual(mode(homes / 'locked'), 0o700)
            self.assertEqual(mode(outside), 0o700)


if __name__ == '__main__':
    unittest.main()
