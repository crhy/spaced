"""Issue #429: friendly per-kind sound device names and icon kinds, offline.

The naming layer is pure and imports from overlays/usr/lib/spaced-linux with
no audio server, no /sys reads and no system settings — this exercises it with
representative device descriptors only.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'overlays/usr/lib/spaced-linux'
sys.path.insert(0, str(LIB))

import spaced_sound_names as naming  # noqa: E402


class SoundDeviceNameTests(unittest.TestCase):
    def test_icon_kinds_are_the_fixed_set(self):
        self.assertEqual(set(naming.ICON_KINDS), {
            'speakers', 'headphones', 'microphone', 'webcam',
            'hdmi_output', 'digital'})

    def test_onboard_analog_output_is_speakers(self):
        name, kind = naming.classify({
            'name': 'alsa_output.pci-0000_00_1f.3.analog-stereo',
            'media_class': 'audio/sink', 'bus': 'pci',
            'driver': 'snd-hda-intel', 'ports': ['analog-output'],
            'onboard': True})
        self.assertEqual(kind, 'speakers')
        self.assertEqual(name, 'Speakers (onboard audio)')

    def test_headphone_port_is_headphones_named_by_connector(self):
        name, kind = naming.classify({
            'name': 'alsa_output.pci-0000_00_1f.3.analog-stereo',
            'media_class': 'audio/sink', 'bus': 'pci',
            'driver': 'snd-hda-intel', 'ports': ['headphones'],
            'onboard': True, 'connector': 'green jack'})
        self.assertEqual(kind, 'headphones')
        self.assertEqual(name, 'Headphones (onboard audio, green jack)')

    def test_usb_microphone_is_named_by_product(self):
        name, kind = naming.classify({
            'name': 'alsa_input.usb-Blue_Microphones_Yeti',
            'media_class': 'audio/source', 'bus': 'usb',
            'ports': ['analog-input-mic'], 'product': 'Blue Yeti'})
        self.assertEqual(kind, 'microphone')
        self.assertEqual(name, 'Blue Yeti microphone (USB)')

    def test_webcam_microphone_is_its_own_kind(self):
        name, kind = naming.classify({
            'name': 'alsa_input.usb-Galayimage_USB2_0_Camera',
            'media_class': 'audio/source', 'bus': 'usb',
            'ports': ['analog-input-mic'], 'product': 'Galyimage',
            'webcam': True})
        self.assertEqual(kind, 'webcam')
        self.assertEqual(name, 'Galyimage webcam microphone')

    def test_nvidia_hdmi_sink_carries_the_gpu_it_drives(self):
        name, kind = naming.classify({
            'name': 'alsa_output.pci-0000_01_00.1.stereo-fallback',
            'media_class': 'audio/sink', 'bus': 'pci',
            'driver': 'HDA NVidia', 'ports': ['hdmi-stereo'],
            'gpu': 'RTX 4070 Ti SUPER', 'monitor': 'LG monitor'})
        self.assertEqual(kind, 'hdmi_output')
        self.assertEqual(name, 'LG monitor (HDMI on RTX 4070 Ti SUPER)')

    def test_port_type_wins_over_a_generic_driver_string(self):
        # "HD-Audio Generic" names by its port, not by the driver string.
        _, kind = naming.classify({
            'name': 'alsa_output.pci-0000_06_00.1.analog-stereo',
            'media_class': 'audio/sink', 'bus': 'pci',
            'driver': 'HD-Audio Generic', 'ports': ['analog-output']})
        self.assertEqual(kind, 'speakers')

    def test_optical_output_is_digital(self):
        name, kind = naming.classify({
            'name': 'alsa_output.pci-0000_00_1b.0.iec958-stereo',
            'media_class': 'audio/sink', 'bus': 'pci',
            'driver': 'snd-hda-intel', 'ports': ['iec958-stereo']})
        self.assertEqual(kind, 'digital')
        self.assertEqual(name, 'Digital output (optical)')

    def test_driver_only_hdmi_still_names_the_gpu(self):
        name, kind = naming.classify({
            'name': 'HDA NVidia', 'media_class': 'audio/sink', 'bus': 'pci',
            'driver': 'HDA NVidia', 'gpu': 'RTX 4070 Ti SUPER'})
        self.assertEqual(kind, 'hdmi_output')
        self.assertEqual(name, 'Monitor (HDMI on RTX 4070 Ti SUPER)')

    def test_unknown_device_falls_back_to_raw_name_with_no_kind(self):
        name, kind = naming.classify({
            'name': 'alsa_output.exotic-unrecognised-device',
            'media_class': 'mystery'})
        self.assertIsNone(kind)
        self.assertEqual(name, 'alsa_output.exotic-unrecognised-device')

    def test_empty_descriptor_falls_back_honestly(self):
        name, kind = naming.classify({})
        self.assertIsNone(kind)
        self.assertEqual(name, 'Unknown audio device')

    def test_non_mapping_descriptor_is_rejected(self):
        with self.assertRaises(TypeError):
            naming.classify(['not', 'a', 'mapping'])

    def test_every_recognised_kind_has_a_symbolic_icon(self):
        # #429 wants real icons: every kind resolves to a symbolic icon, and
        # the unknown fallback to the generic one — never a PCI card.
        for kind in naming.ICON_KINDS:
            icon = naming.ICON_NAMES[kind]
            self.assertTrue(icon.endswith('-symbolic'))
        self.assertEqual(naming.ICON_NAMES[None], 'audio-x-generic-symbolic')


if __name__ == '__main__':
    unittest.main()
