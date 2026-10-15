"""Issue #283: the Voxa Welcome installs a pinned, checksummed Ollama."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'overlays/usr/lib/spaced-linux/spaced-ollama-install'
POLICY = ROOT / 'overlays/usr/share/polkit-1/actions/com.spacedlinux.ollama.policy'


@unittest.skipUnless(shutil.which('zstd') and shutil.which('curl'), 'requires zstd and curl')
class OllamaInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.server = self.temp / 'release'
        self.server.mkdir()
        self.prefix = self.temp / 'prefix'
        self.drm = self.temp / 'drm'
        self.drm.mkdir()
        self.base = self.archive('ollama-linux-amd64.tar.zst', {'bin/ollama': '#!/bin/sh\necho base\n',
                                                                 'lib/ollama/libbase.so': 'base'})
        self.rocm = self.archive('ollama-linux-amd64-rocm.tar.zst', {'lib/ollama/rocm/librocm.so': 'rocm'})

    def archive(self, name, files):
        tree = self.temp / f'tree-{name}'
        for path, text in files.items():
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            (tree / path).write_text(text)
            if path.startswith('bin/'):
                (tree / path).chmod(0o755)
        subprocess.run(['tar', '--zstd', '-cf', str(self.server / name), '-C', str(tree), '.'], check=True)
        data = (self.server / name).read_bytes()
        return f'{name} {hashlib.sha256(data).hexdigest()} {len(data)}'

    def gpu(self, vendor):
        device = self.drm / 'card0/device'
        device.mkdir(parents=True)
        (device / 'vendor').write_text(vendor + '\n')

    def run_helper(self, archives=None, *args):
        env = dict(os.environ, SPACED_OLLAMA_TEST='1', SPACED_OLLAMA_TEST_URL=self.server.as_uri(),
                   SPACED_OLLAMA_TEST_ARCHIVES='\n'.join(archives or [self.base, self.rocm]),
                   SPACED_OLLAMA_TEST_PREFIX=str(self.prefix),
                   SPACED_OLLAMA_TEST_CACHE=str(self.temp / 'cache'),
                   SPACED_OLLAMA_TEST_DRM=str(self.drm))
        return subprocess.run(['bash', str(HELPER), *args], env=env, capture_output=True,
                              text=True, timeout=60)

    def test_installs_the_base_archive_and_reports_progress(self):
        self.gpu('0x10de')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.access(self.prefix / 'bin/ollama', os.X_OK))
        self.assertTrue((self.prefix / 'lib/ollama/libbase.so').exists())
        self.assertFalse((self.prefix / 'lib/ollama/rocm').exists())
        self.assertIn('SPACED_PROGRESS:100', result.stdout.splitlines())
        self.assertEqual(list((self.temp / 'cache').iterdir()), [])

    def test_amd_gpus_also_get_the_rocm_libraries(self):
        self.gpu('0x1002')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.prefix / 'lib/ollama/rocm/librocm.so').exists())
        self.assertTrue((self.prefix / 'lib/ollama/libbase.so').exists())

    def test_checksum_mismatch_installs_nothing(self):
        name, _, size = self.base.split()
        result = self.run_helper([f'{name} {"0" * 64} {size}'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('does not match the checksum', result.stderr)
        self.assertFalse(self.prefix.exists())
        self.assertFalse((self.temp / 'cache' / name).exists())

    def test_existing_installation_is_left_alone(self):
        (self.prefix / 'bin').mkdir(parents=True)
        (self.prefix / 'bin/ollama').write_text('#!/bin/sh\n')
        (self.prefix / 'bin/ollama').chmod(0o755)
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('already installed', result.stdout)
        self.assertFalse((self.prefix / 'lib').exists())

    def test_refuses_arguments(self):
        self.assertEqual(self.run_helper(None, '--prefix=/').returncode, 2)


class PolicyTests(unittest.TestCase):
    def test_root_only_without_test_mode_and_pinned(self):
        text = HELPER.read_text()
        self.assertIn('[ "$(id -u)" -eq 0 ] ||', text)
        self.assertRegex(text, r'ollama-linux-amd64\.tar\.zst [0-9a-f]{64} \d+')
        self.assertIn('sha256sum --check', text)
        policy = POLICY.read_text()
        self.assertIn('>/usr/lib/spaced-linux/spaced-ollama-install<', policy)
        self.assertIn('<allow_any>no</allow_any>', policy)


if __name__ == '__main__':
    unittest.main()
