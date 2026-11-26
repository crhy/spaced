"""Printing package and end-to-end release-gate contracts."""
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'overlays/usr/lib/spaced-linux/spaced-configure-printing'
NETWORK_TEST = ROOT / 'scripts/tests/printing-network-test.sh'


class PrintingNetworkTests(unittest.TestCase):
    def test_cups_browsed_is_an_explicit_image_and_meta_dependency(self):
        manifest = (ROOT / 'config/packages.yaml').read_text(encoding='utf-8')
        packages = set(re.findall(r'^\s+-\s+([^\s#]+)', manifest, re.MULTILINE))
        self.assertTrue({'cups', 'cups-browsed', 'cups-client', 'cups-filters',
                         'cups-ipp-utils', 'system-config-printer'}.issubset(packages))
        control = (ROOT / 'packages/spaced-meta/DEBIAN/control').read_text(
            encoding='utf-8')
        self.assertIn('cups-browsed', control)
        settings_control = (
            ROOT / 'packages/spaced-mate-default-settings/DEBIAN/control'
        ).read_text(encoding='utf-8')
        self.assertIn('cups-browsed', settings_control)

    def test_spaced_pins_lan_queue_policy_and_preserves_admin_choice(self):
        self.assertTrue(POLICY.stat().st_mode & 0o111)
        text = POLICY.read_text(encoding='utf-8')
        self.assertIn('CreateIPPPrinterQueues All', text)
        self.assertIn("grep -Eq '^[[:space:]]*CreateIPPPrinterQueues", text)
        self.assertIn('update-rc.d "$service" defaults', text)

        hook = (ROOT / 'scripts/iso/configure.d/50-services-boot.sh').read_text(
            encoding='utf-8')
        postinst = (ROOT / 'packages/spaced-mate-default-settings/DEBIAN/postinst').read_text(
            encoding='utf-8')
        self.assertIn('/usr/lib/spaced-linux/spaced-configure-printing', hook)
        self.assertIn('/usr/lib/spaced-linux/spaced-configure-printing', postinst)
        self.assertIn('invoke-rc.d cups-browsed restart', postinst)

    def test_configure_printing_runs_idempotently_and_keeps_legacy_browsing_off(self):
        import os, subprocess, tempfile
        script = ROOT / 'overlays/usr/lib/spaced-linux/spaced-configure-printing'
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / 'cups-browsed.conf'
            env = dict(os.environ, SPACED_CUPS_BROWSED_CONF=str(conf),
                       SPACED_INIT_DIR=str(Path(tmp) / 'no-init.d'))
            conf.write_text('# upstream defaults\nCreateIPPPrinterQueues LocalOnly\n'.replace('CreateIPP', '# CreateIPP'))
            for _ in range(2):
                subprocess.run(['sh', str(script)], env=env, check=True)
            text = conf.read_text()
            self.assertEqual(text.count('\nCreateIPPPrinterQueues All'), 1)
            self.assertEqual(text.count('\nBrowseRemoteProtocols none'), 1)
            conf.write_text('CreateIPPPrinterQueues LocalOnly\nBrowseRemoteProtocols dnssd\n')
            subprocess.run(['sh', str(script)], env=env, check=True)
            self.assertEqual(conf.read_text(),
                             'CreateIPPPrinterQueues LocalOnly\nBrowseRemoteProtocols dnssd\n')

    def test_printing_scripts_parse_and_avoid_process_wide_kills(self):
        for script in (POLICY, NETWORK_TEST,
                       ROOT / 'scripts/vm/qemu/network-services-gate.sh',
                       ROOT / 'scripts/vm/qemu/samba-network-gate.sh'):
            result = subprocess.run(['bash', '-n', str(script)], text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, f'{script}: {result.stderr}')
            self.assertNotIn('pkill', script.read_text(encoding='utf-8'))

    def test_network_test_requires_discovery_queue_and_delivery(self):
        text = NETWORK_TEST.read_text(encoding='utf-8')
        self.assertIn('ippfind', text)
        self.assertIn('service_running cups', text)
        self.assertIn('service_running cups-browsed', text)
        self.assertIn('queue_owned_by_cups_browsed', text)
        self.assertIn('lp -d "$QUEUE_NAME"', text)
        self.assertIn('find "$SPOOL_DIR" -type f -size +0c', text)


if __name__ == '__main__':
    unittest.main()
