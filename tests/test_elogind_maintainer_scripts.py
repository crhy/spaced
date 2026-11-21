"""Generate actual debhelper scripts, then execute with harmless service stubs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('dh_installinit'), 'requires debhelper (release build host)')
class ElogindMaintainerScripts(unittest.TestCase):
    def test_upgrade_never_stops_or_restarts_but_removal_still_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            debian = root / 'debian'
            debian.mkdir()
            (debian / 'control').write_text('Source: elogind\nSection: admin\nPriority: optional\nMaintainer: Test <test@example.org>\nBuild-Depends: debhelper-compat (= 13)\n\nPackage: elogind\nArchitecture: any\nDescription: test\n')
            (debian / 'elogind.init').write_text('#!/bin/sh\nexit 0\n')
            subprocess.run(['dh_installinit', '--no-stop-on-upgrade'], cwd=root, check=True, capture_output=True)
            def snippet(kind):
                paths = list(debian.rglob('*' + kind + '*.debhelper')) + list(debian.rglob(kind + '.service'))
                self.assertEqual(len(paths), 1, list(debian.rglob('*')))
                return paths[0].read_text()
            postinst = snippet('postinst')
            prerm = snippet('prerm')
            # Only substitute the init-file existence probe, never service actions.
            postinst = postinst.replace('/etc/init.d/elogind', str(debian / 'elogind.init'))
            prerm = prerm.replace('/etc/init.d/elogind', str(debian / 'elogind.init'))
            (debian / 'elogind.init').chmod(0o755)
            fakebin = root / 'bin'
            fakebin.mkdir()
            log = root / 'actions'
            for name in ('invoke-rc.d', 'update-rc.d'):
                stub = fakebin / name
                stub.write_text('#!/bin/sh\nprintf "%s %s\\n" "' + name + '" "$*" >> "$ACTION_LOG"\n')
                stub.chmod(0o755)
            env = dict(os.environ, PATH=str(fakebin) + ':' + os.environ['PATH'], ACTION_LOG=str(log), DPKG_ROOT='')
            for action, version in [('configure', ''), ('configure', '257.13-1'), ('abort-upgrade', '257.13-1')]:
                log.write_text('')
                subprocess.run(['sh', '-ec', postinst, 'postinst', action, version], env=env, check=True)
                self.assertNotRegex(log.read_text(), r'\b(stop|restart|try-restart)\b')
                if action == 'configure':
                    self.assertIn('elogind start', log.read_text())
            log.write_text('')
            subprocess.run(['sh', '-ec', prerm, 'prerm', 'upgrade', 'next'], env=env, check=True)
            self.assertEqual(log.read_text(), '')
            subprocess.run(['sh', '-ec', prerm, 'prerm', 'remove'], env=env, check=True)
            self.assertIn('elogind stop', log.read_text())

    def test_build_applies_packaging_patch(self):
        patch = ROOT / 'patches/elogind/0003-preserve-session-on-upgrade.patch'
        self.assertIn('dh_installinit --no-stop-on-upgrade', patch.read_text())
        self.assertIn(patch.name, (ROOT / 'scripts/iso/build-elogind.sh').read_text())
