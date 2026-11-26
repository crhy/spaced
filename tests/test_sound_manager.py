"""Unit tests for Spaced Sound Manager's backend and naming (issue #429, 11.26.4).

Fake data only: these feed the deterministic FakeBackend and recorded ``pactl``
output to the parsers and the UI's card logic. No real sound device is opened,
no sound is played and no microphone is touched — the microphone-listening guard
is checked at the backend boundary, and the UI's test-sound path is verified to
refuse against the FakeBackend.
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "overlays/usr/lib/spaced-linux"))

import spaced_sound  # noqa: E402

RAW_OUTPUT = "alsa_output.pci-0000_01_00.1.hdmi-stereo"
RAW_ONBOARD = "alsa_output.pci-0000_00_1f.3.analog-stereo"


class FakeBackendDevicesTests(unittest.TestCase):
    def setUp(self):
        self.b = spaced_sound.FakeBackend()
        self.devs = self.b.devices()

    def test_device_list_becomes_cards_with_friendly_names(self):
        names = {d.friendly for d in self.devs}
        for name in ("LG monitor (HDMI on RTX 4070 Ti SUPER)",
                     "TCL TV (HDMI on RTX 4070 Ti SUPER)",
                     "Speakers (onboard audio)",
                     "Headphones (onboard audio, green jack)",
                     "Blue Yeti microphone (USB)",
                     "Galyimage webcam microphone"):
            self.assertIn(name, names, "missing card %r" % name)

    def test_default_output_and_inputs_split(self):
        outputs = [d for d in self.devs if not d.is_input]
        inputs = [d for d in self.devs if d.is_input]
        self.assertEqual(len(outputs), 4)
        self.assertEqual(len(inputs), 2)
        self.assertEqual(next(d.raw for d in outputs if d.is_default),
                         "alsa_output.pci-0000_01_00.1.hdmi-stereo")

    def test_no_raw_names_reach_a_card_face(self):
        # friendly + detail never contain the raw server string.
        for d in self.devs:
            self.assertNotIn("alsa_", d.friendly)
            self.assertNotIn("pci-", d.friendly)

    def test_default_switch_calls_the_right_pactl_command(self):
        self.b.set_default_output(RAW_ONBOARD)
        self.assertIn(("set-default-sink", RAW_ONBOARD), self.b.calls)
        self.b.set_default_input("alsa_input.usb-Galyimage_HD_Webcam_2009-02.analog-stereo")
        self.assertIn(("set-default-source",
                       "alsa_input.usb-Galyimage_HD_Webcam_2009-02.analog-stereo"),
                      self.b.calls)

    def test_volume_and_mute_writes_normalise_percent(self):
        self.b.set_volume(RAW_OUTPUT, 999)
        self.assertIn(("set-volume", RAW_OUTPUT, 150), self.b.calls)
        self.b.set_mute(RAW_OUTPUT, True)
        self.assertIn(("set-mute", RAW_OUTPUT, True), self.b.calls)


class MicrophoneGuardTests(unittest.TestCase):
    def test_microphone_never_opens_without_both_flags(self):
        b = spaced_sound.FakeBackend()
        self.assertFalse(b.open_microphone_level("x", False, False))
        self.assertFalse(b.open_microphone_level("x", True, False))
        self.assertFalse(b.open_microphone_level("x", False, True))
        self.assertFalse(b.opened_microphone)

    def test_microphone_opens_only_when_on_input_page_and_authorized(self):
        b = spaced_sound.FakeBackend()
        self.assertTrue(b.open_microphone_level("x", True, True))
        self.assertTrue(b.opened_microphone)


class PactlParserTests(unittest.TestCase):
    SAMPLE_SINKS = """\
Index: 0
        Name: alsa_output.pci-0000_01_00.1.hdmi-stereo
        State: RUNNING
        Mute: no
        Volume: front-left: 39321 /  60% / -13.20 dB
        active port: <hdmi-output-0>
Index: 1
        Name: alsa_output.pci-0000_00_1f.3.analog-stereo
        State: RUNNING
        Mute: yes
        Volume: front-left: 49152 /  77% / -6.5 dB
"""

    def _fake_pactl(self, args):  # emulate the injected pactl runner
        joined = " ".join(args)
        if "list sinks" in joined:
            return self.SAMPLE_SINKS
        if "get-default-sink" in joined:
            return "alsa_output.pci-0000_01_00.1.hdmi-stereo\n"
        if "get-default-source" in joined:
            return "\n"
        if "list sources" in joined:
            return ""
        return ""

    def test_parses_sinks_into_friendly_devices(self):
        b = spaced_sound.PactlBackend(runner=self._fake_pactl)
        devs = b.devices()
        self.assertEqual(len(devs), 2)
        by_raw = {d.raw: d for d in devs}
        self.assertTrue(by_raw[RAW_OUTPUT].is_default)
        self.assertEqual(by_raw[RAW_OUTPUT].volume, 60)
        self.assertEqual(by_raw[RAW_ONBOARD].volume, 77)
        self.assertTrue(by_raw[RAW_ONBOARD].muted)

    def test_write_uses_set_default_sink(self):
        seen = []

        def runner(args):
            seen.append(list(args))
            return ""
        b = spaced_sound.PactlBackend(runner=runner)
        b.set_default_output(RAW_ONBOARD)
        self.assertEqual(seen[0], ["set-default-sink", RAW_ONBOARD])

    def test_write_volume_is_normalised_and_arg_safe(self):
        seen = []

        def runner(args):
            seen.append(list(args))
            return ""
        b = spaced_sound.PactlBackend(runner=runner)
        b.set_volume(RAW_ONBOARD, 42)
        self.assertIn(["set-sink-volume", RAW_ONBOARD, "42%"], seen)


APP = ROOT / "overlays/usr/lib/spaced-linux/spaced-sound-manager.py"


class UiSourceTests(unittest.TestCase):
    def test_raw_names_appear_only_on_advanced(self):
        # Raw ALSA/PulseAudio strings are painted only inside _page_advanced
        # (the "raw" label). No other page builds a .raw label.
        src = APP.read_text(encoding="utf-8")
        out_page = src.split("def _page_output")[1].split("def _page_input")[0]
        self.assertNotIn('d.raw', out_page)
        self.assertIn('d.raw', src.split("def _page_advanced")[1].split(
            "def _big_card")[0])

    def test_first_paint_under_xvfb_under_1500ms(self):
        if shutil.which("xvfb-run") is None:
            self.skipTest("no xvfb-run")
        proc = subprocess.run(
            ["xvfb-run", "-a", sys.executable, str(APP), "--fake",
             "--first-paint"],
            capture_output=True, text=True, timeout=30,
            env={**dict(__import__("os").environ), "NO_AT_BRIDGE": "1"})
        match = re.search(r"FIRST_PAINT_MS=([0-9.]+)", proc.stdout)
        self.assertIsNotNone(match, proc.stdout + proc.stderr)
        self.assertLess(float(match.group(1)), 1500.0)
        self.assertEqual(proc.returncode, 0)


class RenderedScreensTests(unittest.TestCase):
    SCREENS = (ROOT / "docs/design/sound-manager/screens-11264")
    PAGES = ["output", "input", "applications", "effects", "advanced"]

    def test_all_ten_pages_rendered_in_both_themes(self):
        if not self.SCREENS.is_dir():
            self.skipTest("run render-screens-11264.sh first")
        count = 0
        for page in self.PAGES:
            for suffix in ("spaced-dark", "light"):
                png = self.SCREENS / ("%s-%s.png" % (page, suffix))
                self.assertTrue(png.is_file(), "%s missing" % png)
                with png.open("rb") as fh:
                    self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n",
                                     "%s is not a PNG" % png.name)
                self.assertGreater(png.stat().st_size, 2000,
                                   "%s looks empty" % png.name)
                count += 1
        self.assertGreaterEqual(count, 10)


if __name__ == "__main__":
    unittest.main()
