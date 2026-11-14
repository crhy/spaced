"""Argument and text checks for the 11.26 vs 11.26.1 release-measure script.

These cases never start QEMU: every invocation below exits during argument or
setting validation, so no VM, network, root, display or hardware is needed.
"""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/release-measure.sh'

# Every number the release comparison in docs/releases/11.26.1/MEASUREMENTS.md
# is built from has to be reported by the script.
METRICS = (
    'iso_size_bytes',
    'iso_sha256_expected',
    'desktop_ready_seconds',
    'uptime_at_desktop_ready_s',
    'mem_used_mib',
    'process_count',
    'top10_rss_kib',
    'context_switches_per_s',
    'interrupts_per_s',
    'idle_cpu_percent',
    'diskstats-at-ready',
    'device=',
    "emit('io_%s_per_s'",
    "'read_bytes'",
    'apt_get_check',
    'dpkg_audit',
    'package_count',
    'display_repair_nr_switches_delta',
    'display_repair_cpu_jiffies_delta',
    'display_repair_sleep_children_seen',
)


class ReleaseMeasureScriptTests(unittest.TestCase):
    def run_script(self, *args, env=None):
        environ = {'PATH': '/usr/bin:/bin'}
        if env:
            environ.update(env)
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=30, env=environ)

    def test_script_exists_and_parses(self):
        self.assertTrue(SCRIPT.is_file(), f'missing {SCRIPT}')
        result = subprocess.run(['bash', '-n', str(SCRIPT)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_usage_without_arguments(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: release-measure.sh ISO', result.stdout + result.stderr)

    def test_missing_iso_is_rejected_without_booting(self):
        result = self.run_script('does-not-exist.iso')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('ISO not found', result.stdout + result.stderr)
        self.assertNotIn('QEMU PID', result.stdout)

    def test_bad_run_label_is_rejected_without_booting(self):
        result = self.run_script(str(ROOT / 'VERSION'), '../evil')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Invalid run label', result.stdout + result.stderr)
        self.assertNotIn('QEMU PID', result.stdout)

    def test_bad_numeric_setting_is_rejected_without_booting(self):
        result = self.run_script(str(ROOT / 'VERSION'), '1',
                                 env={'SPACED_MEASURE_IDLE_SECONDS': 'soon'})
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Invalid numeric VM setting', result.stdout + result.stderr)
        self.assertNotIn('QEMU PID', result.stdout)

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
        result = subprocess.run([shellcheck, str(SCRIPT)], text=True,
                                capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_headless_vm_stopped_by_recorded_pid(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertNotIn('pkill -f', text)
        self.assertNotIn('-display gtk', text)
        self.assertIn('-display none', text)
        self.assertIn('trap cleanup EXIT', text)
        self.assertIn('QEMU_PID=$!', text)
        self.assertIn('kill "$QEMU_PID"', text)

    def test_same_vm_flags_as_the_live_check_script(self):
        text = SCRIPT.read_text(encoding='utf-8')
        for flag in ('-enable-kvm', '-cpu host', '-cdrom "$ISO"', '-boot order=d',
                     '-rtc base=utc', '-vga std', 'hostfwd=tcp:127.0.0.1:'):
            self.assertIn(flag, text)
        self.assertIn('SPACED_QEMU_RAM:-4096', text)
        self.assertIn('SPACED_QEMU_CPUS:-4', text)

    def test_measures_every_compared_metric(self):
        text = SCRIPT.read_text(encoding='utf-8')
        for metric in METRICS:
            self.assertIn(metric, text, f'{metric} is never reported')
        self.assertIn('INFO:', text)
        self.assertIn('RESULT: PASS passed=$PASSED failed=$FAILED', text)
        self.assertIn('RESULT: FAIL passed=$PASSED failed=$FAILED', text)

    def test_idle_window_is_sampled_inside_the_guest(self):
        text = SCRIPT.read_text(encoding='utf-8')
        for marker in ('===MARK stat0===', '===MARK t0===', '===MARK t1===',
                       '===MARK stat1===', '===MARK interrupts0===',
                       '===MARK interrupts1==='):
            self.assertIn(marker, text)
        # /proc/stat gives the boot and idle CPU numbers without systemd-analyze.
        self.assertIn('/proc/stat', text)
        self.assertIn('/proc/interrupts', text)
        self.assertIn('/proc/diskstats', text)
        self.assertIn('/proc/$p/sched', text)

    def test_measurement_never_changes_the_guest(self):
        text = SCRIPT.read_text(encoding='utf-8')
        for forbidden in ('apt-get install', 'apt-get update', 'dpkg -i', 'rm -rf',
                          'systemctl', 'shutdown', 'reboot', 'write', 'dd if='):
            self.assertNotIn(forbidden, text)

    def test_display_repair_helper_is_matched_without_matching_itself(self):
        text = SCRIPT.read_text(encoding='utf-8')
        # pgrep -f would otherwise also match the su/ssh command line that runs
        # the search, so the pattern has to break its own name.
        self.assertIn("pgrep -f 'spaced-display[-]repair'", text)


if __name__ == '__main__':
    unittest.main()
