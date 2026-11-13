"""Argument, text and pure-logic checks for the issue #413 reused-home scripts.

These cases never start QEMU and never need a VM, network, root, a display or
this PC's hardware: every script invocation below exits during argument
handling, and the OCR word matcher of gui.sh is exercised through a synthetic
tesseract TSV file.
"""
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'scripts/vm/qemu/gui.sh'
SCRIPT = ROOT / 'scripts/vm/qemu/install-reuse-home.sh'
GUI_SOURCE = shlex.quote(str(GUI))


def bash(source):
    return subprocess.run(['bash', '-c', source], text=True, capture_output=True,
                          timeout=60)


class ReuseHomeScriptTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=30)

    def test_both_scripts_exist_and_parse(self):
        for script in (GUI, SCRIPT):
            with self.subTest(script=script.name):
                self.assertTrue(script.is_file(), f'missing {script}')
                result = subprocess.run(['bash', '-n', str(script)], text=True,
                                        capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_usage_without_arguments(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: install-reuse-home.sh ISO', result.stdout + result.stderr)

    def test_missing_iso_is_rejected_without_booting(self):
        result = self.run_script('does-not-exist.iso')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('ISO not found', result.stdout + result.stderr)
        self.assertNotIn('QEMU PID', result.stdout)

    def test_shellcheck_is_clean(self):
        shellcheck = shutil.which('shellcheck')
        if shellcheck is None:
            self.skipTest('shellcheck is not installed')
        for script in (GUI, SCRIPT):
            with self.subTest(script=script.name):
                result = subprocess.run([shellcheck, str(script)], text=True,
                                        capture_output=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_never_uses_pkill_or_a_visible_qemu_window(self):
        for script in (GUI, SCRIPT):
            with self.subTest(script=script.name):
                text = script.read_text(encoding='utf-8')
                self.assertNotIn('pkill -f', text)
                self.assertNotIn('-display gtk', text)
        started = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('-display none', started)
        self.assertIn('trap cleanup EXIT', started)
        self.assertIn('QEMU_PID=$!', started)

    def test_the_test_drives_the_real_installer_and_checks_the_result(self):
        """The point of the task: the real Calamares flow, verified on disk."""
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('/usr/local/bin/install-spaced-linux', text)
        self.assertIn('Replace a partition', text)
        self.assertIn('as home partition', text)
        self.assertIn('os-prober', text)
        self.assertIn('blkid -s UUID -o value /dev/vda2', text)
        self.assertIn('mount -o ro /dev/vda1 /mnt/t', text)
        self.assertIn('RESULT: PASS fstab_home=', text)
        self.assertIn('RESULT: FAIL fstab_home=', text)
        self.assertIn('keep_olduser=', text)
        self.assertIn('rescue_tools_installed=', text)

    def test_gui_helpers_are_used_and_reject_bad_arguments_without_a_vm(self):
        gui_text = GUI.read_text(encoding='utf-8')
        for function in ('gui_shot', 'gui_text', 'gui_find', 'gui_click',
                         'gui_click_xy', 'gui_type', 'gui_key', 'gui_wait'):
            self.assertIn(f'{function}() {{', gui_text, f'gui.sh has no {function}()')
        self.assertIn('screendump', gui_text)
        self.assertIn('tesseract', gui_text)
        self.assertIn('ImageOps.invert', gui_text)
        self.assertIn('xdotool', gui_text)
        for call in ('gui_find ""', 'gui_wait "x" many', 'gui_click_xy a b',
                     'gui_type ""', 'gui_key ""', 'gui_shot ""'):
            with self.subTest(call=call):
                result = bash(f'. {GUI_SOURCE}; {call}')
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_shot_without_a_qmp_socket_fails_without_touching_a_vm(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = shlex.quote(tmp)
            result = bash(f'. {GUI_SOURCE}; SPACED_VM_QMP_SOCKET={tmp_dir}/nope.sock '
                          f'gui_shot {tmp_dir}/screen.png')
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('no QMP socket', result.stdout + result.stderr)
            self.assertFalse(Path(tmp, 'screen.png').exists())

    def tsv(self, rows):
        header = ('level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t'
                  'left\ttop\twidth\theight\tconf\ttext')
        lines = [header]
        for row in rows:
            lines.append('\t'.join(str(field) for field in row))
        return '\n'.join(lines) + '\n'

    def run_finder(self, query, rows, scale=2):
        """Run gui.sh's OCR word matcher over a synthetic tesseract TSV dump."""
        program = bash(f'. {GUI_SOURCE}; printf %s "$GUI_FIND_PY"')
        self.assertEqual(program.returncode, 0, program.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'words.tsv')
            path.write_text(self.tsv(rows), encoding='utf-8')
            return subprocess.run(['python3', '-c', program.stdout, query, str(scale),
                                   str(path)], text=True, capture_output=True, timeout=30)

    @staticmethod
    def word(text, left, top, width=100, height=40, line=1):
        return (5, 1, 1, 1, line, 1, left, top, width, height, 95.0, text)

    def test_finder_divides_the_enlargement_out_and_matches_word_pairs(self):
        rows = [self.word('Install', 600, 200),
                self.word('Spaced', 700, 200, width=120),
                self.word('Linux', 840, 200)]
        result = self.run_finder('spaced linux', rows)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # box 700..940 x 200..240 -> centre (820, 220) at 2x -> (410, 110)
        self.assertEqual(result.stdout.split(), ['410', '110'])
        self.assertEqual(self.run_finder('INSTALL Spaced', rows).returncode, 0)
        self.assertEqual(self.run_finder('not present', rows).returncode, 1)

    def test_finder_does_not_join_words_from_different_lines(self):
        rows = [self.word('Reuse', 600, 200, line=1),
                self.word('partition', 600, 400, line=2)]
        self.assertEqual(self.run_finder('Reuse partition', rows).returncode, 1)


if __name__ == '__main__':
    unittest.main()
