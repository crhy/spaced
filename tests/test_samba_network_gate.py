"""Static and argument checks for the two-VM Samba release gate."""
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/vm/qemu/samba-network-gate.sh'


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
        self.assertIn('Usage: samba-network-gate.sh ISO', result.stderr)
        result = self.run_script('does-not-exist.iso')
        self.assertEqual(result.returncode, 2)
        self.assertIn('ISO not found', result.stderr)

    def test_gate_uses_two_recorded_vms_on_an_isolated_lan(self):
        text = SCRIPT.read_text(encoding='utf-8')
        self.assertEqual(text.count('qemu-system-x86_64 -enable-kvm'), 2)
        self.assertIn('socket,id=lan,listen=', text)
        self.assertIn('socket,id=lan,connect=', text)
        self.assertIn('SERVER_PID=$!', text)
        self.assertIn('CLIENT_PID=$!', text)
        self.assertIn('wait_for_lan_listener', text)
        self.assertNotIn('pkill', text)

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
        network_test = (ROOT / 'scripts/tests/samba-network-test.sh').read_text(encoding='utf-8')
        self.assertIn('standard::target-uri=smb://$address', network_test)
        self.assertIn('standard::display-name=$expected_browse_name', network_test)
        self.assertIn('SMB and GVfs copy round trips', text)


if __name__ == '__main__':
    unittest.main()
