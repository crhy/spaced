"""Offline checks for the cross-OS benchmark harness issue #424 needs first.

These cases never start QEMU: the probe measures the machine it runs on, the
comparator is fed synthetic TSV rows, and every run-bench.sh invocation below
exits while looking for ISOs that are not on this machine, so no VM, network,
root, display or other operating system is needed.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'scripts/vm/bench'
PROBE = BENCH / 'guest-probe.sh'
RUNNER = BENCH / 'run-bench.sh'
COMPARATOR = BENCH / 'compare.py'
MATRIX = BENCH / 'matrix.conf'

# The metric set guest-probe.sh has to emit for whatever machine it runs on,
# matching the names scripts/vm/qemu/release-measure.sh reports.
METRICS = (
    'uptime_at_desktop_ready_s',
    'mem_used_mib',
    'process_count',
    'top10_rss_kib',
    'context_switches_per_s',
    'interrupts_per_s',
    'idle_cpu_percent',
    'diskstats_reads_completed',
    'diskstats_sectors_read',
    'diskstats_mib_read',
    'pkg_manager',
    'package_count',
    'pkg_manager_query_ms',
)

COLUMNS = ('os_label', 'run_label', 'iso_path', 'iso_size_bytes') + METRICS


def tsv(rows):
    lines = ['\t'.join(COLUMNS)]
    for row in rows:
        assert len(row) == len(COLUMNS), f'row has {len(row)} fields, expected {len(COLUMNS)}'
        lines.append('\t'.join(row))
    return '\n'.join(lines) + '\n'


class BenchMatrixTests(unittest.TestCase):
    def run_command(self, argv, env=None, cwd=None):
        environ = {'PATH': '/usr/bin:/bin'}
        if env:
            environ.update(env)
        return subprocess.run([str(item) for item in argv], text=True,
                              capture_output=True, timeout=120, env=environ,
                              cwd=str(cwd) if cwd else None)

    def test_scripts_exist_and_parse(self):
        for path in (PROBE, RUNNER, COMPARATOR, MATRIX):
            self.assertTrue(path.is_file(), f'missing {path}')
        for script in (PROBE, RUNNER):
            result = subprocess.run(['bash', '-n', str(script)], text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
        source = COMPARATOR.read_text(encoding='utf-8')
        self.assertNotIn('import PIL', source)
        self.assertNotIn('import numpy', source)
        self.assertNotIn('import matplotlib', source)

    def test_probe_selftest_reports_every_metric_on_this_machine(self):
        result = self.run_command(['bash', PROBE, '--selftest', '--idle', '1'])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for metric in METRICS:
            emitted = f'INFO: {metric}=' in result.stdout
            skipped = f'SKIP: {metric} not available on this distro' in result.stdout
            self.assertTrue(emitted or skipped,
                             f'{metric} is neither measured nor skipped')
        self.assertIn('RESULT: selftest metrics=', result.stdout)
        self.assertIn('INFO: idle_window_seconds=', result.stdout)

    def test_probe_skips_a_metric_its_machine_cannot_provide(self):
        # The wording the probe promises for a distro without the source of a
        # metric, checked against the script itself because no other OS image
        # exists on this machine to run the probe in.
        text = PROBE.read_text(encoding='utf-8')
        self.assertIn('not available on this distro', text)
        self.assertIn('skip()', text)

    def test_probe_bad_arguments_exit_before_measuring(self):
        for argument in ('--idle', 'soon', '--bogus'):
            result = self.run_command(['bash', PROBE, '--selftest', argument])
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('Usage: guest-probe.sh', result.stdout + result.stderr)
            self.assertNotIn('RESULT:', result.stdout)

    def test_probe_reads_proc_and_its_own_clock_only(self):
        text = PROBE.read_text(encoding='utf-8')
        for source in ('/proc/uptime', '/proc/meminfo', '/proc/stat',
                       '/proc/diskstats', '/proc/version'):
            self.assertIn(source, text, f'{source} is never read')
        for forbidden in ('sudo', 'systemctl', 'apt-get install', 'apt-get update',
                          'dnf install', 'apk add', 'pacman', 'yum', 'shutdown',
                          'reboot', 'pkill', 'curl', 'wget', 'qemu-system-x86_64'):
            self.assertNotIn(forbidden, text,
                             f'the probe must not touch {forbidden}')

    def test_runner_reports_missing_isos_and_still_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            matrix = Path(tmp) / 'matrix.conf'
            matrix.write_text('# synthetic matrix: no ISO on this machine\n'
                              'spaced-linux build/iso/absent.iso\n'
                              'debian build/iso/also-absent.iso\n',
                              encoding='utf-8')
            result = self.run_command(['bash', RUNNER, matrix, '1'],
                                      env={'BENCH_OUT_DIR': tmp,
                                           'BENCH_VM_DIR': str(Path(tmp) / 'vms')},
                                      cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('SKIP: spaced-linux no iso at', result.stdout)
            self.assertIn('SKIP: debian no iso at', result.stdout)
            self.assertIn('RESULT: measured=0 skipped=2', result.stdout)
            self.assertNotIn('Booting', result.stdout)

    def test_runner_with_an_empty_matrix_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            matrix = Path(tmp) / 'matrix.conf'
            matrix.write_text('# nothing fetched yet\n\n', encoding='utf-8')
            result = self.run_command(['bash', RUNNER, matrix, '1'],
                                      env={'BENCH_OUT_DIR': tmp,
                                           'BENCH_VM_DIR': str(Path(tmp) / 'vms')},
                                      cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('SKIP:', result.stdout)
            self.assertIn('RESULT: measured=0 skipped=0', result.stdout)

    def test_runner_stops_the_vm_it_started_by_recorded_pid(self):
        text = RUNNER.read_text(encoding='utf-8')
        self.assertIn('-daemonize -pidfile', text)
        self.assertIn('kill "$pid"', text)
        self.assertNotIn('pkill -f', text)
        self.assertIn('build_common_args', text)
        self.assertIn('-boot order=c', text)
        self.assertIn('-display none', text)
        self.assertIn('guest-probe.sh', text)
        self.assertNotIn('sudo', text)

    def test_matrix_lists_spaced_first(self):
        entries = []
        for line in MATRIX.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            entries.append(line.split())
        self.assertTrue(entries, 'matrix.conf names no operating system')
        self.assertEqual(entries[0][0], 'spaced-linux')
        self.assertGreaterEqual(len(entries[0]), 2,
                                'matrix lines are "<label> <iso-path> [key=value]"')
        self.assertTrue(entries[0][1].endswith('.iso'))
        for option in entries[0][2:]:
            self.assertRegex(option, r'^[a-z]+=')

    def test_comparator_tables_ranking_and_missing_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                ['spaced', '1', 'a.iso', '1633140736', '31.7', '1189', '118',
                 '240000', '40684.9', '19966.0', '19.30', '5874121',
                 '179826366', '87805.8', 'dpkg', '1729', '13'],
                ['debian', '1', 'b.iso', '1000000000', '44.2', '1420', '205',
                 '510000', '52110.2', '24010.5', '27.10', '7120000',
                 '201000000', '98100.0', 'dpkg', '2100', '41'],
                # A third OS whose ISO booted but whose probe measured nothing.
                ['freebsd', '1', 'c.iso', '', '', '', '', '', '', '',
                 '', '', '', '', '', '', ''],
            ]
            path = Path(tmp) / 'rows.tsv'
            path.write_text(tsv(rows), encoding='utf-8')
            svg = Path(tmp) / 'compare.svg'
            result = self.run_command(['python3', COMPARATOR, path,
                                       '--svg', svg])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for metric in METRICS:
                self.assertIn(f'metric: {metric}', result.stdout)
            self.assertIn('| OS | value | note |', result.stdout)
            self.assertIn('| spaced | 1189 | best |', result.stdout)
            self.assertIn('| debian | 1420 |  |', result.stdout)
            self.assertEqual(result.stdout.count('| freebsd | not measured |  |'),
                             len(METRICS))
            self.assertIn('RESULT: oses=3 ranked=12 refused=0', result.stdout)
            self.assertTrue(svg.is_file(), 'no SVG written')
            self.assertTrue(svg.read_text(encoding='utf-8').startswith('<svg '))

    def test_comparator_refuses_to_rank_one_os(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                ['spaced', '1', 'a.iso', '1633140736', '31.7', '1189', '118',
                 '240000', '40684.9', '19966.0', '19.30', '5874121',
                 '179826366', '87805.8', 'dpkg', '1729', '13'],
                # Only one number for the second OS: everything else stays
                # unranked rather than being compared against a single value.
                ['alpine', '1', 'b.iso', '', '22.9', '', '', '', '', '', '',
                 '', '', '', 'apk', '', ''],
            ]
            path = Path(tmp) / 'rows.tsv'
            path.write_text(tsv(rows), encoding='utf-8')
            svg = Path(tmp) / 'compare.svg'
            result = self.run_command(['python3', COMPARATOR, path, '--svg', svg])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('REFUSED: mem_used_mib has data for 1 OS;', result.stdout)
            self.assertIn('ranking needs at least two', result.stdout)
            self.assertIn('REFUSED: process_count has data for 1 OS;', result.stdout)
            self.assertIn('not ranked, fewer than two OSes measured:',
                          svg.read_text(encoding='utf-8'))
            self.assertIn('RESULT: oses=2 ranked=1 refused=11', result.stdout)

    def test_comparator_without_rows_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_command(['python3', COMPARATOR,
                                       Path(tmp) / 'nothing.tsv',
                                       '--svg', Path(tmp) / 'compare.svg'])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('no benchmark rows found', result.stdout)

    def test_metric_lists_agree_across_the_harness(self):
        probe = PROBE.read_text(encoding='utf-8')
        runner = RUNNER.read_text(encoding='utf-8')
        comparator = COMPARATOR.read_text(encoding='utf-8')
        for metric in METRICS:
            for name, text in (('guest-probe.sh', probe),
                               ('run-bench.sh', runner),
                               ('compare.py', comparator)):
                self.assertIn(metric, text,
                              f'{metric} is missing from {name}')

    def test_shellcheck_is_clean(self):
        shellcheck = shutil.which('shellcheck')
        if shellcheck is None:
            self.skipTest('shellcheck is not installed')
        # The scripts are kept clean against shellcheck 0.10+; older releases
        # (for example 0.9 on CI runners) report differently.
        version = subprocess.run([shellcheck, '--version'], text=True,
                                 capture_output=True, timeout=30).stdout
        found = re.search(r'version: (\d+)\.(\d+)', version)
        if not found or (int(found[1]), int(found[2])) < (0, 10):
            self.skipTest('shellcheck 0.10 or newer is required')
        result = subprocess.run([shellcheck, '-S', 'warning', str(PROBE),
                                 str(RUNNER)], text=True,
                                capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
