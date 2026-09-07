"""Exercise the smoke launcher without booting VMs or changing host displays."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/smoke-iso.sh'


class QemuSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.iso = self.root / 'test.iso'
        self.iso.touch()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        SPACED_QEMU_ACCEL='tcg', SPACED_VM_SSH_PORT='65530',
                        SPACED_ISO_SMOKE_TIMEOUT='2', SPACED_QEMU_FIRMWARE='bios',
                        SPACED_QEMU_ARTIFACT_DIR=str(self.root / 'artifacts with spaces'),
                        SPACED_TEST_RECORD=str(self.root / 'qemu.json'))
        for name in ('ssh', 'sshpass'):
            path = self.bin / name
            path.write_text('#!/bin/sh\nexit 1\n')
            path.chmod(0o755)
        qemu = self.bin / 'qemu-system-x86_64'
        qemu.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
record = {'args': args, 'pid': os.getpid()}
for arg in args:
    if 'if=pflash' in arg and 'readonly' not in arg:
        path = pathlib.Path(arg.split('file=',1)[1])
        record['vars_content'] = path.read_text()
        record['vars_mode'] = path.stat().st_mode & 0o777
pathlib.Path(os.environ['SPACED_TEST_RECORD']).write_text(json.dumps(record))
if os.environ.get('SPACED_TEST_HOLD'):
    time.sleep(30)
sys.exit(42)
''')
        qemu.chmod(0o755)

    def run_smoke(self):
        result = subprocess.run([str(SCRIPT), str(self.iso)], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_bios_defaults_use_one_gpu_and_two_cpu_two_gib(self):
        self.run_smoke()
        args = json.loads((self.root / 'qemu.json').read_text())['args']
        self.assertEqual(args[args.index('-m') + 1], '2048')
        self.assertEqual(args[args.index('-smp') + 1], '2')
        self.assertEqual(args.count('-vga'), 1)
        self.assertEqual(args[args.index('-vga') + 1], 'std')
        self.assertIn('VGA.vgamem_mb=64', args)
        self.assertFalse(any('if=pflash' in arg for arg in args))
        self.assertTrue(args[args.index('-qmp') + 1].startswith('unix:'))
        self.assertNotIn('-daemonize', args)

    def test_uefi_copies_vars_and_4k_remains_single_gpu(self):
        code, vars = self.root / 'CODE.fd', self.root / 'VARS.fd'
        code.write_text('code')
        vars.write_text('pristine variables')
        self.env.update(SPACED_QEMU_FIRMWARE='uefi', SPACED_OVMF_CODE=str(code),
                        SPACED_OVMF_VARS=str(vars), SPACED_QEMU_XRES='3840', SPACED_QEMU_YRES='2160')
        self.run_smoke()
        record = json.loads((self.root / 'qemu.json').read_text())
        args = record['args']
        self.assertEqual(record['vars_content'], 'pristine variables')
        self.assertEqual(record['vars_mode'], 0o600)
        self.assertEqual(vars.read_text(), 'pristine variables')
        drives = [arg for arg in args if arg.startswith('if=pflash')]
        self.assertEqual(len(drives), 2)
        self.assertIn('readonly=on', drives[0])
        self.assertNotIn(str(vars), drives[1])
        self.assertIn('VGA.xres=3840', args)
        self.assertIn('VGA.yres=2160', args)
        self.assertEqual(args.count('-vga'), 1)
        self.assertNotIn('VGA,', ' '.join(args))

    def test_partial_resolution_is_rejected_before_launch(self):
        self.env['SPACED_QEMU_XRES'] = '3840'
        self.env.pop('SPACED_QEMU_YRES', None)
        result = self.run_smoke()
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / 'qemu.json').exists())

    def test_termination_reaps_only_the_owned_qemu(self):
        self.env['SPACED_TEST_HOLD'] = '1'
        self.env['SPACED_ISO_SMOKE_TIMEOUT'] = '60'
        process = subprocess.Popen([str(SCRIPT), str(self.iso)], env=self.env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        record = self.root / 'qemu.json'
        deadline = time.monotonic() + 3
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(record.exists())
        pid = json.loads(record.read_text())['pid']
        process.terminate()
        process.wait(timeout=8)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == '__main__':
    unittest.main()
