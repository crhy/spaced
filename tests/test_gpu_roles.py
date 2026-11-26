"""Exercise GPU role selection without touching host graphics."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

LIB = Path(__file__).parents[1] / "overlays/usr/lib/spaced-linux"


def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(LIB / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, "path", [str(LIB), *sys.path]):
        loader.exec_module(module)
    return module


roles = load("roles", "spaced-gpu-roles")

INTEGRATED_AND_DISCRETE = """0000:00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics 630 (Mobile) [8086:3e9b] (rev 02)
0000:00:1f.3 Audio device [0403]: Intel Corporation Cannon Lake PCH cAVS [8086:a348] (rev 10)
0000:01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA104 [GeForce RTX 3070 Laptop GPU] [10de:249d] (rev a1)
0000:01:00.1 Audio device [0403]: NVIDIA Corporation GA104 High Definition Audio Controller [10de:10dc] (rev a1)
0000:00:1f.0 ISA bridge [0601]: Intel Corporation Cannon Lake PCH LPC [8086:a30e] (rev 10)
"""

AMD_APU_AND_DISCRETE = """0000:00:08.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Renoir [Radeon Graphics] [1002:1636] (rev c4)
0000:03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Nitron XTX [Radeon RX] [1002:73df] (rev c8)
0000:03:00.1 Audio device [0403]: Advanced Micro Devices, Inc. [AMD/ATI] [1002:ab07]
"""

SINGLE_GPU = """0000:01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA104 [GeForce RTX 3070] [10de:2484] (rev a1)
0000:01:00.1 Audio device [0403]: NVIDIA Corporation GA104 High Definition Audio Controller [10de:10dc] (rev a1)
"""

NO_GPU = """0000:00:1f.3 Audio device [0403]: Intel Corporation Cannon Lake PCH cAVS [8086:a348] (rev 10)
0000:00:1f.0 ISA bridge [0601]: Intel Corporation Cannon Lake PCH LPC [8086:a30e] (rev 10)
0000:01:00.0 Non-Volatile memory controller [0108]: Intel Corporation SSD [8086:2723]
"""


class EnumerationTests(unittest.TestCase):
    def test_only_display_controllers_are_enumerated(self):
        devices = roles.parse_lspci(INTEGRATED_AND_DISCRETE)
        self.assertEqual([device.slot for device in devices], ["0000:00:02.0", "0000:01:00.0"])
        self.assertTrue(all(device.class_code in ("0300", "0302") for device in devices))

    def test_classification(self):
        intel, nvidia = roles.parse_lspci(INTEGRATED_AND_DISCRETE)
        self.assertTrue(roles.is_integrated(intel))
        self.assertFalse(roles.is_integrated(nvidia))
        apu, amd_discrete = roles.parse_lspci(AMD_APU_AND_DISCRETE)
        self.assertTrue(roles.is_integrated(apu))
        self.assertFalse(roles.is_integrated(amd_discrete))


class RoleChoiceTests(unittest.TestCase):
    def test_igpu_drives_the_desktop_and_dgpu_stays_free(self):
        desktop, free = roles.choose_roles(roles.parse_lspci(INTEGRATED_AND_DISCRETE))
        self.assertEqual((desktop.slot, free.slot), ("0000:00:02.0", "0000:01:00.0"))

    def test_amd_apu_drives_the_desktop_and_dgpu_stays_free(self):
        desktop, free = roles.choose_roles(roles.parse_lspci(AMD_APU_AND_DISCRETE))
        self.assertEqual((desktop.slot, free.slot), ("0000:00:08.0", "0000:03:00.0"))

    def test_single_gpu_has_no_free_gpu(self):
        desktop, free = roles.choose_roles(roles.parse_lspci(SINGLE_GPU))
        self.assertEqual(desktop.slot, "0000:01:00.0")
        self.assertIsNone(free)

    def test_no_gpu_yields_no_roles(self):
        self.assertEqual(roles.choose_roles(roles.parse_lspci(NO_GPU)), (None, None))


class XConfigTests(unittest.TestCase):
    def lspci_file(self, root, text):
        path = root / "lspci.txt"
        path.write_text(text)
        return path

    def test_two_gpus_write_a_snippet_that_names_the_igpu_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "xorg.conf.d/20-spaced-gpu-roles.conf"
            roles.main(["--lspci", str(self.lspci_file(root, INTEGRATED_AND_DISCRETE)), "--out", str(out)])
            config = out.read_text()
            self.assertIn('Option     "PrimaryDevice" "true"', config)
            self.assertIn('BusID      "PCI:0:2:0"', config)
            self.assertIn('Section "ServerLayout"', config)
            self.assertIn("01:00.0", config.split("Comment")[1])
            self.assertNotIn("PCI:1:0:0", config)

    def test_single_gpu_writes_no_snippet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "xorg.conf.d/20-spaced-gpu-roles.conf"
            roles.main(["--lspci", str(self.lspci_file(root, SINGLE_GPU)), "--out", str(out)])
            self.assertFalse(out.exists())

    def test_no_gpu_writes_no_snippet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "xorg.conf.d/20-spaced-gpu-roles.conf"
            roles.main(["--lspci", str(self.lspci_file(root, NO_GPU)), "--out", str(out)])
            self.assertFalse(out.exists())


class SysvinitRuleTests(unittest.TestCase):
    def test_tool_never_writes_a_service_unit_or_service_manager_command(self):
        text = (LIB / "spaced-gpu-roles").read_text()
        self.assertNotIn("systemd", text)
        self.assertNotIn("systemctl", text)


if __name__ == "__main__":
    unittest.main()
