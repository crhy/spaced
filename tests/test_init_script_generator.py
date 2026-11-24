"""Checks for scripts/spaced-init-gen, the systemd-unit to sysvinit generator.

These cases never touch systemd, the network or root: the generator only parses
a unit file's text and prints a script, and every failing invocation exits
during argument handling. The generated scripts are checked with ``bash -n``
and for an unknown argument only, so no daemon is ever started.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'spaced-init-gen'


def run_gen(args):
    return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                          capture_output=True, timeout=30)


class InitScriptGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write_unit(self, name, text):
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding='utf-8')
        return path

    def generate(self, unit_path, *extra):
        return run_gen([*extra, str(unit_path)])

    def test_script_exists_is_executable_and_parses(self):
        self.assertTrue(SCRIPT.is_file(), f'missing {SCRIPT}')
        self.assertTrue(os.access(SCRIPT, os.X_OK), 'generator is not executable')
        result = subprocess.run(['bash', '-n', str(SCRIPT)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generator_source_never_names_systemctl(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('systemctl', text)

    def test_missing_unit_file_prints_usage_and_exits_2(self):
        result = run_gen([str(Path(self.tmp.name) / 'does-not-exist.service')])
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: spaced-init-gen', result.stdout + result.stderr)

    def test_unit_without_execstart_refuses_and_exits_1(self):
        unit = self.write_unit('nostart.service',
                               '[Unit]\nDescription=Nothing to start\n\n'
                               '[Service]\nExecStop=/usr/bin/true\n')
        result = self.generate(unit)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('no ExecStart', result.stdout + result.stderr)

    def test_simple_daemon_output_is_valid_and_carries_fields(self):
        unit = self.write_unit('simpled.service',
                               '[Unit]\nDescription=Simple example daemon\n'
                               'After=network.target\n\n[Service]\nType=simple\n'
                               'ExecStart=/usr/bin/simpled --verbose\n'
                               'ExecStop=/usr/bin/simpled --shutdown\n'
                               'PIDFile=/run/simpled.pid\n')
        result = self.generate(unit)
        self.assertEqual(result.returncode, 0, result.stderr)
        script = result.stdout

        generated = Path(self.tmp.name) / 'simpled'
        generated.write_text(script, encoding='utf-8')
        syntax = subprocess.run(['bash', '-n', str(generated)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        # INIT INFO identity matches the unit.
        self.assertIn('# Provides:          simpled', script)
        self.assertIn('# Short-Description: Simple example daemon', script)
        # The start branch runs start-stop-daemon on the ExecStart binary.
        self.assertIn('start-stop-daemon --start', script)
        self.assertIn('--exec /usr/bin/simpled', script)
        # PIDFile and the ExecStop command are carried through.
        self.assertIn('PIDFILE=/run/simpled.pid', script)
        self.assertIn('/usr/bin/simpled --shutdown', script)

    def test_user_unit_carries_user_and_network_requirement(self):
        unit = self.write_unit('userd.service',
                               '[Unit]\nDescription=Privileged daemon\n'
                               'After=network.target\n\n[Service]\n'
                               'User=daemon\nGroup=daemon\n'
                               'ExecStart=/opt/userd/run\n')
        result = self.generate(unit)
        self.assertEqual(result.returncode, 0, result.stderr)
        script = result.stdout
        self.assertIn('# Required-Start:    $network', script)
        self.assertIn('--chuid daemon:daemon', script)

    def test_generated_script_rejects_unknown_argument_with_exit_2(self):
        unit = self.write_unit('argd.service',
                               '[Unit]\nDescription=Arg daemon\n\n[Service]\n'
                               'ExecStart=/usr/bin/argd\n')
        script = self.generate(unit).stdout
        generated = Path(self.tmp.name) / 'argd'
        generated.write_text(script, encoding='utf-8')
        generated.chmod(0o755)
        result = subprocess.run(['sh', str(generated), 'bogus'], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Usage:', result.stdout + result.stderr)

    def test_dash_o_writes_the_script_to_a_file(self):
        unit = self.write_unit('tofile.service',
                               '[Unit]\nDescription=To file\n\n[Service]\n'
                               'ExecStart=/usr/bin/tofile\n')
        out = Path(self.tmp.name) / 'written'
        result = self.generate(unit, '-o', str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('# Provides:          tofile', out.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
