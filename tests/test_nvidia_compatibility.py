"""Exercise driver selection and postboot checks without modifying host graphics."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


LIB = Path(__file__).parents[1] / "overlays/usr/lib/spaced-linux"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, LIB / filename)
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(LIB), *sys.path]):
        spec.loader.exec_module(module)
    return module


compat = load("compat", "spaced-nvidia-compat.py")
state = load("state", "spaced_nvidia_state.py")
gi = types.SimpleNamespace(require_version=lambda *_: None)
with patch.dict(sys.modules, {"gi": gi, "gi.repository": types.SimpleNamespace(Gtk=object)}):
    postboot = load("postboot", "spaced-nvidia-postboot.py")


class HardwareCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.database = self.root / "gpus.json"
        # These IDs/legacy branches match NVIDIA's supported-gpus.json.
        self.database.write_text(json.dumps({"chips": [
            {"devid": "0x0F02", "name": "GT 730 Fermi", "legacybranch": "390.xx"},
            {"devid": "0x1287", "name": "GT 730 Kepler", "legacybranch": "470.xx"},
            {"devid": "0x2484", "name": "RTX 3070", "features": ["kernelopen"]},
        ]}))

    def gpu(self, slot, device_id, vendor="0x10de", device_class="0x030000"):
        device = self.root / "bus/pci/devices" / slot
        device.mkdir(parents=True)
        for name, value in {"vendor": vendor, "class": device_class, "device": device_id,
                            "subsystem_vendor": "0x10de", "subsystem_device": "0x0000"}.items():
            (device / name).write_text(value)

    def test_current_gpu_and_non_graphics_devices(self):
        self.gpu("0000:01:00.0", "0x2484")
        self.gpu("0000:01:00.1", "0xffff", device_class="0x040300")
        self.gpu("0000:00:02.0", "0xffff", vendor="0x8086")
        compat.check_hardware(self.database, self.root)

    def test_both_gt730_variants_stop_before_latest_driver(self):
        for device_id, branch in (("0x0f02", "390.xx"), ("0x1287", "470.xx")):
            with self.subTest(device_id=device_id):
                self.gpu(device_id, device_id)
                with self.assertRaisesRegex(ValueError, "legacy"):
                    compat.check_hardware(self.database, self.root)
                for file in (self.root / "bus/pci/devices" / device_id).iterdir():
                    file.unlink()
                (self.root / "bus/pci/devices" / device_id).rmdir()

    def test_modern_gpu_does_not_hide_incompatible_second_gpu(self):
        self.gpu("0000:01:00.0", "0x2484")
        self.gpu("0000:02:00.0", "0x1287")
        with self.assertRaisesRegex(ValueError, "470.xx"):
            compat.check_hardware(self.database, self.root)

    def test_unknown_gpu_fails_closed(self):
        self.gpu("0000:01:00.0", "0xffff")
        with self.assertRaisesRegex(ValueError, "absent"):
            compat.check_hardware(self.database, self.root)

    def test_no_nvidia_display_is_not_success(self):
        self.gpu("0000:01:00.1", "0xffff", device_class="0x040300")
        with self.assertRaisesRegex(ValueError, "No NVIDIA"):
            compat.check_hardware(self.database, self.root)


class RecommendationTests(unittest.TestCase):
    def test_supported_upstream_package_commands(self):
        for package in ("nvidia-open", "cuda-drivers", "cuda-drivers-580"):
            self.assertEqual(compat.recommended_package(
                f"Detected GPUs:\n  RTX 3070\nPlease copy and paste:\n  sudo apt-get install -Vy {package}\n"), package)

    def test_unexpected_commands_and_shell_syntax_are_rejected(self):
        for command in ("sudo apt-get purge nvidia-open", "sudo apt-get install -Vy nvidia-open systemd-sysv",
                        "sudo apt-get install -Vy nvidia-open; reboot", "sudo apt-get install -Vy $(reboot)",
                        "sudo apt-get install -Vy nvidia-open && reboot", "sudo apt-get install --allow-unauthenticated nvidia-open",
                        "sudo apt-get install -Vy nvidia-open\nsudo apt-get install -Vy cuda-drivers", "No recommendation"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                compat.recommended_package(command)


class PostbootOpenGLTests(unittest.TestCase):
    NVIDIA = "direct rendering: Yes\nOpenGL vendor string: NVIDIA Corporation\nOpenGL renderer string: NVIDIA RTX 3070"
    INTEL = "direct rendering: Yes\nOpenGL vendor string: Intel\nOpenGL renderer string: Mesa Intel UHD"
    AMD = "direct rendering: Yes\nOpenGL vendor string: AMD\nOpenGL renderer string: AMD Radeon Graphics"
    SOFTWARE = "direct rendering: Yes\nOpenGL vendor string: Mesa\nOpenGL renderer string: llvmpipe"

    def test_dedicated_nvidia_uses_default_renderer(self):
        with patch.object(postboot, "run", return_value=(0, self.NVIDIA, "")) as run:
            failures, details = postboot.check_opengl()
        self.assertEqual(failures, [])
        run.assert_called_once_with(["glxinfo", "-B"])

    def test_hybrid_intel_or_amd_desktop_verifies_nvidia_offload(self):
        for desktop in (self.INTEL, self.AMD):
            with self.subTest(desktop=desktop), patch.object(postboot, "run", side_effect=[(0, desktop, ""), (0, self.NVIDIA, "")]) as run:
                failures, details = postboot.check_opengl()
                self.assertEqual(failures, [])
                self.assertEqual(run.call_args.args[0], ["env", "__NV_PRIME_RENDER_OFFLOAD=1", "__GLX_VENDOR_LIBRARY_NAME=nvidia", "glxinfo", "-B"])

    def test_failed_prime_is_not_accepted_as_hybrid_success(self):
        with patch.object(postboot, "run", side_effect=[(0, self.INTEL, ""), (1, "", "GLXBadContext")]):
            failures, _ = postboot.check_opengl()
        self.assertTrue(any("PRIME" in error for error in failures))

    def test_software_desktop_fails_even_when_nvidia_offload_works(self):
        with patch.object(postboot, "run", side_effect=[(0, self.SOFTWARE, ""), (0, self.NVIDIA, "")]):
            failures, _ = postboot.check_opengl()
        self.assertTrue(any("software" in error for error in failures))


class VerificationStateTests(unittest.TestCase):
    def test_reboot_and_acknowledgement_belong_to_one_transaction(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(state.Path, "home", return_value=Path(directory)):
            root = Path(directory)
            pending, boot = root / "pending", root / "boot"
            pending.write_text("boot_id=before\nkernel=test\n")
            boot.write_text("before\n")
            self.assertTrue(state.awaiting_reboot(pending, boot))
            boot.write_text("after\n")
            self.assertFalse(state.awaiting_reboot(pending, boot))
            self.assertFalse(state.installation_verified(pending))
            acknowledgement = state.ack_path(pending)
            acknowledgement.parent.mkdir(parents=True)
            acknowledgement.write_text("verified desktop\n")
            self.assertTrue(state.installation_verified(pending))
            pending.write_text("boot_id=another-install\n")
            self.assertFalse(state.installation_verified(pending))

    def test_old_marker_can_still_be_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            pending = Path(directory) / "pending"
            pending.write_text("kernel=old-installer\n")
            self.assertFalse(state.awaiting_reboot(pending))


if __name__ == "__main__":
    unittest.main()
