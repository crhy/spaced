"""Issue #440 packaging: the statereason.py override must survive dpkg.

/usr/share/system-config-printer/statereason.py is a file owned by Debian's
system-config-printer-common, so the Spaced package that ships the corrected
copy cannot simply take the path: dpkg would refuse the install or a Debian
upgrade would silently restore the buggy file.  spaced-mate-default-settings
therefore diverts the Debian file to statereason.py.distrib in preinst and
removes the diversion in postrm.  This builds the package in a scratch
directory and checks the maintainer script pair, the staged wrapper, and
that no script mentions systemd.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'packages/spaced-mate-default-settings'
WRAPPER = 'usr/share/system-config-printer/statereason.py'
DIVERTED = WRAPPER + '.distrib'


class PrinterStateReasonDiversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which('dpkg-deb') is None:
            raise unittest.SkipTest('dpkg-deb is not installed')
        cls._tmp = tempfile.TemporaryDirectory(prefix='divert-',
                                               dir=str(ROOT / 'build'))
        tmp = Path(cls._tmp.name)
        stage = tmp / 'pkg'
        shutil.copytree(PKG, stage)
        # The wrapper is staged from overlays/ by build-local-packages.sh;
        # stage it the same way so the scratch build holds real package bytes.
        subprocess.run(['cp', '-a', '--parents', WRAPPER, str(stage)],
                       cwd=ROOT / 'overlays', check=True)
        cls.deb = str(tmp / 'pkg.deb')
        subprocess.run(['dpkg-deb', '--build', str(stage), cls.deb],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def assert_divert_pair(self, script, action):
        self.assertIn('dpkg-divert', script)
        self.assertIn('--package spaced-mate-default-settings', script)
        self.assertIn(f'--divert /{DIVERTED}', script)
        self.assertIn('--rename', script)
        self.assertIn(action, script)
        # Spaced is sysvinit-only (docs/notes/spaced-no-systemd.md).
        self.assertNotIn('systemd', script)

    def test_preinst_diverts_and_postrm_undiverts(self):
        self.assert_divert_pair((PKG / 'DEBIAN/preinst').read_text(), '--add')
        self.assert_divert_pair((PKG / 'DEBIAN/postrm').read_text(), '--remove')

    def test_maintainer_scripts_are_executable(self):
        for script in ('preinst', 'postrm'):
            mode = (PKG / 'DEBIAN' / script).stat().st_mode
            self.assertTrue(mode & 0o100, f'DEBIAN/{script} must be executable')

    def test_build_settings_paths_stage_the_wrapper(self):
        script = (ROOT / 'scripts/iso/build-local-packages.sh').read_text()
        paths = re.search(r'SETTINGS_PATHS=\(([^)]*)\)', script, re.S).group(1)
        self.assertIn(WRAPPER, paths)

    def test_built_package_ships_wrapper_and_scripts(self):
        listing = subprocess.run(['dpkg-deb', '-c', self.deb],
                                 check=True, capture_output=True,
                                 text=True).stdout
        self.assertIn('/' + WRAPPER, listing)
        self.assertNotIn(DIVERTED, listing)  # the .distrib name is dpkg's job
        ctrl = Path(self.deb).parent / 'ctrl'
        subprocess.run(['dpkg-deb', '-e', self.deb, str(ctrl)],
                       check=True, capture_output=True)
        self.assert_divert_pair((ctrl / 'preinst').read_text(), '--add')
        self.assert_divert_pair((ctrl / 'postrm').read_text(), '--remove')

    def test_wrapper_is_a_thin_override_not_a_full_copy(self):
        wrapper = (ROOT / 'overlays' / WRAPPER).read_text()
        # The diverted module is loaded, not duplicated: the wrapper keeps
        # Debian's future changes by importing it and replacing only the
        # classification and the printing wordings.
        self.assertIn('statereason.py.distrib', wrapper)
        self.assertIn('exec_module', wrapper)
        self.assertIn('StateReason.get_level =', wrapper)
        self.assertLess(len(wrapper.splitlines()), 130)


if __name__ == '__main__':
    unittest.main()
