"""No host graphics changes: all trial mutations use a temporary filesystem."""
import importlib.util
from contextlib import nullcontext
import importlib.machinery
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'overlays/usr/lib/spaced-linux'
spec = importlib.util.spec_from_file_location('spaced_gpu', LIB / 'spaced_gpu.py')
gpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu)
loader = importlib.machinery.SourceFileLoader('gpu_helper_test', str(LIB / 'spaced-gpu-helper'))
helper_spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(helper_spec)
with patch.dict(sys.modules, spaced_gpu=gpu), patch.object(sys, 'path', list(sys.path)):
    loader.exec_module(helper)


def device(pci='0000:10:00.0', driver='amdgpu'):
    return dict(pci=pci, driver=driver, vendor='AMD' if driver == 'amdgpu' else 'NVIDIA',
                connectors=[dict(status='connected', enabled='enabled', name='HDMI-A-1')])


class DiscoveryTests(unittest.TestCase):
    def test_compute_uses_uuid_not_enumeration(self):
        card = device(driver='nvidia')
        card['uuid'] = 'GPU-b38e5856-b893-b0e3-5e2e-74253b1fe303'
        self.assertEqual(gpu.compute_environment(card), {'CUDA_VISIBLE_DEVICES': card['uuid']})

    def test_compute_missing_or_invalid_identity_refused(self):
        for value in (None, '0', 'GPU-; touch /tmp/unsafe', 'GPU-' + '-' * 36):
            card = dict(device(driver='nvidia'), uuid=value)
            with self.assertRaises(ValueError):
                gpu.compute_environment(card)

    def test_non_cuda_driver_refused(self):
        with self.assertRaisesRegex(ValueError, 'ROCm'):
            gpu.compute_environment(device())

    def test_pci_normalization(self):
        self.assertEqual(gpu.normalize_pci('00000000:0A:00.0'), '0000:0a:00.0')
        self.assertIsNone(gpu.normalize_pci('0000:01:00.0\nSection "Device"'))

    def test_missing_tools(self):
        with patch.object(gpu.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(gpu.command(['missing']), '')

    def test_hung_driver_probe(self):
        with patch.object(gpu.subprocess, 'run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 8)):
            self.assertEqual(gpu.command(['nvidia-smi']), '')

    def test_identity_not_nvidia_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for address in ('0000:01:00.0', '0000:08:00.0'):
                path = root / 'bus/pci/devices' / address
                path.mkdir(parents=True)
                (path / 'class').write_text('0x030000')
                (path / 'vendor').write_text('0x10de')
            def run(args):
                if args[0] == 'lspci':
                    return ''
                if args[1] == '--query-gpu=pci.bus_id,uuid':
                    return ('00000000:08:00.0, GPU-8c4b1594-c374-3f99-1354-953ba52ab76a\n'
                            '00000000:01:00.0, GPU-b38e5856-b893-b0e3-5e2e-74253b1fe303\n')
                return '00000000:08:00.0, Second GPU, 8192, 12, 610\n00000000:01:00.0, First GPU, 16384, 20, 610\n'
            found = gpu.discover(root, run)
            self.assertEqual([(g['pci'], g['name'], g['vram_total']) for g in found],
                             [('0000:01:00.0', 'First GPU', 16384), ('0000:08:00.0', 'Second GPU', 8192)])
            self.assertEqual(found[0]['uuid'], 'GPU-b38e5856-b893-b0e3-5e2e-74253b1fe303')
            self.assertEqual(found[1]['uuid'], 'GPU-8c4b1594-c374-3f99-1354-953ba52ab76a')

    def test_intel_arc_discrete_and_igpu_by_bus_position(self):
        # issue #426 review: Intel makes discrete cards too (Arc). The iGPU
        # enumerates on the root bus; the Arc sits behind a PCIe bridge.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for address in ('0000:00:02.0', '0000:03:00.0'):
                path = root / 'bus/pci/devices' / address
                path.mkdir(parents=True)
                (path / 'class').write_text('0x030000')
                (path / 'vendor').write_text('0x8086')

            def run(args):
                if args[0] == 'lspci':
                    return ('0000:00:02.0 VGA compatible controller: Intel UHD Graphics\n'
                            '0000:03:00.0 Display controller: Intel Arc A770\n')
                return ''
            found = {g['pci']: g for g in gpu.discover(root, run)}
            self.assertEqual([(g['vendor'], g['family']) for g in found.values()],
                             [('Intel', 'Intel'), ('Intel', 'Intel')])
            self.assertTrue(found['0000:00:02.0']['integrated'])
            self.assertFalse(found['0000:03:00.0']['integrated'])

    def test_3d_controller_is_discrete_whatever_the_bus(self):
        # class 0x0302 (3D controller, no display engine) is never on-board.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'bus/pci/devices' / '0000:04:00.0'
            path.mkdir(parents=True)
            (path / 'class').write_text('0x030200')
            (path / 'vendor').write_text('0x8086')

            def run(args):
                return '0000:04:00.0 3D controller: Intel Arc A310\n' if args[0] == 'lspci' else ''
            self.assertFalse(gpu.discover(root, run)[0]['integrated'])

    def test_aspeed_bmc_server_classified_as_other(self):
        # Matrox, ASPEED, Moore Threads and VIA are Other, by vendor id; the
        # BMC graphics chip is on the board (integrated), not an add-in card.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'bus/pci/devices' / '0000:01:00.0'
            path.mkdir(parents=True)
            (path / 'class').write_text('0x030000')
            (path / 'vendor').write_text('0x1a03')
            (path / 'boot_vga').write_text('1')

            def run(args):
                if args[0] == 'lspci':
                    return '0000:01:00.0 VGA compatible controller: ASPEED AST2500\n'
                return ''
            found = gpu.discover(root, run)
            self.assertEqual([(g['vendor'], g['family'], g['integrated']) for g in found],
                             [('ASPEED', 'Other', True)])
            self.assertIn('Keep a monitor connected', gpu.recommendation(found))
            self.assertIn('modesetting', gpu.xorg_config(dict(found[0], driver='ast')))

    def test_pcie_generation_from_link_speed(self):
        self.assertEqual(gpu.pcie_generation('16.0 GT/s PCIe'), 'PCIe 4.0')
        self.assertEqual(gpu.pcie_generation('8.0 GT/s PCIe'), 'PCIe 3.0')
        self.assertEqual(gpu.pcie_generation('2.5 GT/s PCIe'), 'PCIe 1.0')
        self.assertEqual(gpu.pcie_generation('Unknown'), '')

    def test_missing_sysfs(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(gpu.discover(Path(directory), lambda _: ''), [])

    def test_mesa_offload_uses_pci(self):
        self.assertEqual(gpu.offload_environment(device(), []), {'DRI_PRIME': 'pci-0000_10_00_0'})

    def test_multiple_nvidia_refuses_guess(self):
        cards = [device('0000:01:00.0', 'nvidia'), device('0000:08:00.0', 'nvidia')]
        with self.assertRaisesRegex(ValueError, 'will not guess'):
            gpu.offload_environment(cards[1], cards)

    def test_single_nvidia(self):
        card = device(driver='nvidia')
        self.assertEqual(gpu.offload_environment(card, [card])['__GLX_VENDOR_LIBRARY_NAME'], 'nvidia')

    def test_unknown_offload(self):
        with self.assertRaises(ValueError):
            gpu.offload_environment(device(driver='vfio-pci'), [])

    def test_recommendation_uses_connected_not_boot_vga(self):
        amd = device()
        amd['connectors'] = []
        nvidia = device(driver='nvidia')
        nvidia['connectors'][0]['enabled'] = 'disabled'
        self.assertIn('Move the monitor cable', gpu.recommendation([amd, nvidia]))


class TrialTests(unittest.TestCase):
    def test_guard_restart_does_not_extend_deadline(self):
        self.stage()
        with patch.object(gpu, 'boot_seconds', return_value=10):
            self.trial.begin_boot('boot-b')
        with patch.object(gpu, 'boot_seconds', return_value=100):
            self.trial.begin_boot('boot-b')
        self.assertEqual(self.trial.load()['deadline_boot_seconds'], 190)

    def test_expired_trial_cannot_be_confirmed(self):
        self.stage()
        with patch.object(gpu, 'boot_seconds', return_value=10):
            self.trial.begin_boot('boot-b')
        with patch.object(gpu, 'boot_seconds', return_value=190):
            with self.assertRaisesRegex(ValueError, 'expired'):
                self.trial.confirm('boot-b')
        self.assertEqual(self.trial.load()['phase'], 'trial')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trial = gpu.Trial(self.root)
        self.card = device()

    def stage(self):
        return self.trial.stage(self.card, 'boot-a')

    def test_bus_id_is_decimal(self):
        self.assertIn('BusID "PCI:16@0:0:0"', gpu.xorg_config(self.card))

    def test_injection_rejected(self):
        with self.assertRaises(ValueError):
            gpu.xorg_config(device('0000:01:00.0"\nEndSection'))

    def test_unsupported_driver(self):
        with self.assertRaises(ValueError):
            gpu.xorg_config(device(driver='vfio-pci'))

    def test_connected_monitor_required(self):
        self.card['connectors'] = []
        with self.assertRaisesRegex(ValueError, 'Connect a monitor'):
            self.stage()
        self.assertFalse(self.trial.state.exists())

    def test_stage_does_not_begin_current_boot(self):
        self.stage()
        self.assertFalse(self.trial.begin_boot('boot-a'))
        self.assertEqual(self.trial.load()['phase'], 'staged')

    def test_confirm_only_after_boot(self):
        self.stage()
        with self.assertRaises(ValueError):
            self.trial.confirm('boot-a')
        self.assertTrue(self.trial.begin_boot('boot-b'))
        self.trial.confirm('boot-b')
        self.assertEqual(self.trial.load()['phase'], 'confirmed')
        self.assertFalse(self.trial.begin_boot('boot-c'))

    def test_cannot_confirm_a_different_boot(self):
        self.stage()
        self.trial.begin_boot('boot-b')
        with self.assertRaises(ValueError):
            self.trial.confirm('boot-c')

    def test_prevents_second_pending_trial(self):
        self.stage()
        with self.assertRaises(ValueError):
            self.stage()

    def test_revert_removes_only_managed_file(self):
        self.stage()
        other = self.trial.config.parent / '20-spaced-amdgpu.conf'
        other.write_text('keep me')
        self.trial.revert()
        self.assertFalse(self.trial.config.exists())
        self.assertEqual(other.read_text(), 'keep me')
        self.assertEqual(self.trial.load()['phase'], 'reverted')

    def test_revert_restores_previous_confirmed_assignment(self):
        first = self.stage()['candidate']
        self.trial.begin_boot('boot-b')
        self.trial.confirm('boot-b')
        self.trial.stage(device('0000:08:00.0', 'nvidia'), 'boot-b')
        self.trial.revert()
        self.assertEqual(self.trial.config.read_text(), first)
        self.trial.stage(self.card, 'boot-b')  # A reverted assignment is usable again.

    def test_external_edits_preserved(self):
        self.stage()
        self.trial.config.write_text('administrator edit')
        with self.assertRaisesRegex(ValueError, 'outside GPU Manager'):
            self.trial.revert()
        self.assertEqual(self.trial.config.read_text(), 'administrator edit')

    def test_symlink_preserved(self):
        self.trial.config.parent.mkdir(parents=True)
        target = self.root / 'custom'
        target.write_text('custom')
        self.trial.config.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.stage()
        self.assertEqual(target.read_text(), 'custom')

    def test_unknown_owned_path_preserved(self):
        self.trial.config.parent.mkdir(parents=True)
        self.trial.config.write_text('custom')
        with self.assertRaisesRegex(ValueError, 'external edits'):
            self.stage()

    def test_custom_xorg_layout_preserved(self):
        path = self.root / 'etc/X11/xorg.conf.d/custom.conf'
        path.parent.mkdir(parents=True)
        path.write_text('Section "ServerLayout"\nEndSection\n')
        with self.assertRaisesRegex(ValueError, 'Custom Xorg layout'):
            self.stage()

    def test_outputclass_does_not_block(self):
        path = self.root / 'etc/X11/xorg.conf.d/20-spaced-amdgpu.conf'
        path.parent.mkdir(parents=True)
        path.write_text('Section "OutputClass"\nEndSection\n')
        self.stage()

    def test_write_failure_retains_recoverable_journal(self):
        original = gpu.atomic_write
        def fail_config(path, content):
            if path == self.trial.config:
                raise OSError('disk full')
            return original(path, content)
        with patch.object(gpu, 'atomic_write', side_effect=fail_config):
            with self.assertRaises(OSError):
                self.stage()
        self.assertEqual(self.trial.load()['phase'], 'staged')
        # No configuration directory may have been created before the failure.
        self.trial.revert()

    def test_confirm_checks_config(self):
        self.stage()
        self.trial.begin_boot('boot-b')
        self.trial.config.write_text('external edit')
        with self.assertRaises(ValueError):
            self.trial.confirm('boot-b')


class WatchdogTests(unittest.TestCase):
    def test_restart_uses_persisted_deadline(self):
        trial = Mock()
        trial.load.return_value = {'phase': 'trial', 'trial_boot': 'new', 'deadline_boot_seconds': 180}
        with patch.object(helper, 'Trial', return_value=trial), \
             patch.object(helper, 'boot_id', return_value='new'), \
             patch.object(helper, 'driver_lock', side_effect=nullcontext), \
             patch.object(helper, 'boot_seconds', side_effect=[179, 181]), \
             patch.object(helper.time, 'sleep') as sleep, \
             patch.object(helper.subprocess, 'run') as run:
            helper.watchdog()
        sleep.assert_called_once_with(2)
        trial.revert.assert_called_once()
        run.assert_called_once()

    def test_confirmation_during_countdown_prevents_restart(self):
        trial = Mock()
        trial.load.side_effect = [
            {'phase': 'trial', 'trial_boot': 'new', 'deadline_boot_seconds': 180},
            {'phase': 'confirmed'}]
        with patch.object(helper, 'Trial', return_value=trial), \
             patch.object(helper, 'boot_id', return_value='new'), \
             patch.object(helper, 'driver_lock', side_effect=nullcontext), \
             patch.object(helper, 'boot_seconds', return_value=100), \
             patch.object(helper.subprocess, 'run') as run:
            helper.watchdog()
        trial.revert.assert_not_called()
        run.assert_not_called()

    def run_watchdog(self, trial, boot='new'):
        with patch.object(helper, 'Trial', return_value=trial), \
             patch.object(helper, 'boot_id', return_value=boot), \
             patch.object(helper, 'driver_lock', side_effect=nullcontext), \
             patch.object(helper, 'boot_seconds', return_value=181), \
             patch.object(helper.subprocess, 'run') as run:
            helper.watchdog()
            return run

    def test_expiration_restores_before_restart(self):
        trial = Mock()
        trial.load.return_value = {'phase': 'trial', 'trial_boot': 'new'}
        run = self.run_watchdog(trial)
        trial.revert.assert_called_once()
        run.assert_called_once_with(['/usr/sbin/service', 'lightdm', 'restart'], check=True, timeout=60)

    def test_confirmation_prevents_restart(self):
        trial = Mock()
        trial.load.side_effect = [{'phase': 'trial', 'trial_boot': 'new'}, {'phase': 'confirmed'}]
        run = self.run_watchdog(trial)
        trial.revert.assert_not_called()
        run.assert_not_called()

    def test_ordinary_boot_does_nothing(self):
        trial = Mock()
        trial.begin_boot.return_value = False
        run = self.run_watchdog(trial)
        run.assert_not_called()
        trial.revert.assert_not_called()

    def test_failed_restore_must_not_restart(self):
        trial = Mock()
        trial.load.return_value = {'phase': 'trial', 'trial_boot': 'new'}
        trial.revert.side_effect = ValueError('admin edit')
        with self.assertRaisesRegex(ValueError, 'admin edit'):
            self.run_watchdog(trial)


class DriverInterlockTests(unittest.TestCase):
    def test_pending_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'reboot-required'
            marker.write_text('boot_id=current\n')
            os.utime(marker, (10, 10))
            self.assertTrue(gpu.driver_reboot_pending(root, 'current', 20, lambda _: 'GPU'))
            self.assertFalse(gpu.driver_reboot_pending(root, 'next', 20, lambda _: 'GPU'))
            self.assertTrue(gpu.driver_reboot_pending(root, 'next', 20, lambda _: ''))

    def test_legacy_empty_recovery_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'recovery-reboot-required'
            marker.touch()
            os.utime(marker, (30, 30))
            self.assertTrue(gpu.driver_reboot_pending(root, 'current', 20))
            self.assertFalse(gpu.driver_reboot_pending(root, 'next', 40))

    def test_shared_lock_and_driver_interlock_shipped(self):
        source = (LIB / 'spaced-nvidia-helper').read_text()
        self.assertIn('trial.json', source)
        self.assertIn('transaction.lock', source)
        paths = (ROOT / 'scripts/iso/build-local-packages.sh').read_text()
        for path in ('etc/init.d/spaced-gpu-guard', 'etc/xdg/autostart/spaced-gpu-trial.desktop',
                     'usr/share/polkit-1/actions/com.spacedlinux.gpu.policy'):
            self.assertIn(path, paths)


if __name__ == '__main__':
    unittest.main()
