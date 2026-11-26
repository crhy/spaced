"""Static and argument checks for the two-VM network-services release gate."""
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/network-services-gate.sh'
LEGACY_SCRIPT = ROOT / 'scripts/vm/qemu/samba-network-gate.sh'


class SambaNetworkGateTests(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], text=True,
                              capture_output=True, timeout=30)

    def test_script_parses(self):
        result = subprocess.run(['bash', '-n', str(SCRIPT)], text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_usage_and_missing_iso_stop_before_qemu(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn('Usage: network-services-gate.sh ISO', result.stderr)
        result = self.run_script('does-not-exist.iso')
        self.assertEqual(result.returncode, 2)
        self.assertIn('ISO not found', result.stderr)

    def test_gate_uses_two_recorded_vms_on_an_isolated_lan(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertEqual(text.count('qemu-system-x86_64 "${QEMU_ACCEL_ARGS[@]}"'), 2)
        self.assertIn('SPACED_QEMU_ACCEL', text)
        self.assertIn('tcg,thread=multi', text)
        self.assertIn('socket,id=lan,listen=', text)
        self.assertIn('socket,id=lan,connect=', text)
        self.assertIn('SERVER_PID=$!', text)
        self.assertIn('CLIENT_PID=$!', text)
        self.assertIn('wait_for_lan_listener', text)
        self.assertNotIn('pkill', text)

    def test_legacy_samba_name_is_a_thin_compatibility_wrapper(self):
        text = LEGACY_SCRIPT.read_text(encoding='utf-8')
        self.assertIn('exec "$script_dir/network-services-gate.sh" "$@"', text)
        self.assertNotIn('qemu-system-x86_64', text)

    def test_candidate_repository_upgrades_both_guests_before_testing(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('SIGNED_APT_REPOSITORY', text)
        self.assertIn('upgrade_guest server', text)
        self.assertIn('upgrade_guest client', text)
        self.assertLess(text.index('upgrade_guest server'),
                        text.index('# Install the exact repository tests'))
        self.assertIn('signed-by=', text)
        self.assertIn("apt-get -o APT::Update::Error-Mode=any update", text)

    def test_gate_rejects_an_unknown_accelerator_before_qemu(self):
        iso = ROOT / 'VERSION'
        result = subprocess.run(
            ['bash', str(SCRIPT), str(iso)], text=True, capture_output=True,
            timeout=30, env={'PATH': '/usr/bin:/bin', 'SPACED_QEMU_ACCEL': 'bogus'})
        self.assertEqual(result.returncode, 2)
        self.assertIn('SPACED_QEMU_ACCEL must be kvm or tcg', result.stderr)

    def test_gate_runs_the_physical_network_test_modes(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('samba-network-test.sh local', text)
        self.assertIn('samba-network-test.sh serve', text)
        self.assertIn('samba-network-test.sh peer 192.168.76.10', text)
        self.assertIn('SPACED_REQUIRE_GVFS_GUEST=1', text)
        self.assertIn('SPACED_REQUIRE_NETWORK_BROWSE=1', text)
        self.assertIn('SPACED_EXPECT_BROWSE_NAME=SPACED-SHARE', text)
        self.assertIn('DBUS_SESSION_BUS_ADDRESS', text)
        self.assertIn('/proc/$pid/environ', text)
        self.assertIn("printf '%s\\\\n' '$hostname' > /etc/hostname", text)
        self.assertIn("configure_lan \"$SERVER_SSH_PORT\" 52:54:00:76:00:10 192.168.76.10 spaced-share", text)
        self.assertIn("configure_lan \"$CLIENT_SSH_PORT\" 52:54:00:76:00:11 192.168.76.11 spaced-client", text)
        self.assertIn('nmcli connection add type ethernet', text)
        self.assertIn('nmcli connection up spaced-test-lan', text)
        self.assertIn('/etc/init.d/smbd stop', text)
        self.assertIn('/etc/init.d/spaced-wsdd stop', text)
        self.assertIn('wait_for_guest_service "$port" smbd', text)
        self.assertIn('wait_for_guest_service "$port" spaced-wsdd', text)
        self.assertNotIn('nmcli device set "$iface" managed no', text)
        self.assertNotIn('ip addr add', text)
        self.assertNotIn('/etc/init.d/smbd restart', text)
        self.assertNotIn('/etc/init.d/spaced-wsdd restart', text)
        network_test = (ROOT / 'scripts/tests/samba-network-test.sh').read_text(encoding='utf-8')
        self.assertIn('standard::target-uri=smb://$address', network_test)
        self.assertIn('standard::display-name=$expected_browse_name', network_test)
        self.assertIn('SMB/GVfs copy and IPP print round trips', text)

    def test_gate_runs_real_network_printing_modes(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('printing-network-test.sh serve', text)
        self.assertIn('printing-network-test.sh peer', text)
        self.assertIn('printing-network-test.sh verify', text)
        self.assertIn('printing-network-test.sh stop', text)
        printing_test = (ROOT / 'scripts/tests/printing-network-test.sh').read_text(
            encoding='utf-8')
        self.assertIn('ippfind', printing_test)
        self.assertIn('service_running cups-browsed', printing_test)
        self.assertIn('lp -d "$QUEUE_NAME"', printing_test)
        self.assertIn('document_delivered', printing_test)


if __name__ == '__main__':
    unittest.main()
