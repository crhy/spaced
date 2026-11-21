"""Design-task guards for Spaced Sound Manager (issue #429, 11.26.4).

Design-only task: these tests keep the design documents honest and prove the mockups
exist and were rendered by the fake-data prototype. No shipped code is involved and no
audio device is ever opened: the prototype's test-sound path refuses to run unless a
click flag is present, and the tests below only inspect files and read PNG headers.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = ROOT / "docs/design/sound-manager"
PAGES = ["output", "input", "applications", "effects", "advanced"]


def read(path):
    return path.read_text(encoding="utf-8")


class DesignDocsTests(unittest.TestCase):
    def test_the_three_docs_exist_and_are_substantial(self):
        for name in ("TODAY.md", "DESIGN.md", "ARCHITECTURE.md"):
            path = DESIGN_DIR / name
            self.assertTrue(path.is_file(), f"{name} missing")
            self.assertGreater(len(read(path)), 2000, f"{name} is too thin")

    def test_the_design_stays_sysvinit_only(self):
        # Spaced is sysvinit-only: the design may say it does not use a foreign init, but
        # must never install, name or call one (docs/notes/spaced-no-systemd.md).
        for name in ("DESIGN.md", "ARCHITECTURE.md"):
            text = read(DESIGN_DIR / name)
            lowered = text.lower()
            for banned in ("systemctl", "systemd-networkd", "systemd-user",
                           ".service restart", "service systemd"):
                self.assertNotIn(banned, lowered, f"{banned} named in {name}")
            self.assertIn("sysvinit", lowered, f"{name} forgets the init system")
        # the shipped session is autospawned pulseaudio, not a system daemon
        self.assertIn("pulseaudio.desktop", read(DESIGN_DIR / "ARCHITECTURE.md"))

    def test_today_inventories_every_current_feature(self):
        today = read(DESIGN_DIR / "TODAY.md")
        for feature in ("Sound Effects", "Hardware", "Input", "Output", "Applications",
                        "Profile", "Co_nnector", "Test Speakers", "e_xceed 100%",
                        "No application is currently playing", "Input level",
                        "volume-overamplifiable", "mate-volume-control-status-icon",
                        "mate-volume-control"):
            self.assertIn(feature, today, f"TODAY.md lost track of {feature!r}")

    def test_design_names_the_friendly_names_and_icons_layer(self):
        design = read(DESIGN_DIR / "DESIGN.md")
        for name in ("LG monitor (HDMI on RTX 4070 Ti SUPER)",
                     "Blue Yeti microphone (USB)", "Galyimage webcam microphone",
                     "Speakers (onboard audio)", "Headphones (onboard audio, green jack)"):
            self.assertIn(name, design)
        for icon in ("audio-speakers-symbolic", "audio-headphones-symbolic",
                     "audio-input-microphone-symbolic", "video-display-symbolic"):
            self.assertIn(icon, design)
        # every user-facing string set was written out, not described
        for string in ("Test sound", "Stop", "Muted", "Show my microphone level",
                       "Spaced is listening to your microphone",
                       "Nothing is playing or recording sound right now.",
                       "Sound is not working", "Fix it for me", "Quit",
                       "Sound is back.", "may need to be restarted"):
            self.assertIn(string, design)

    def test_architecture_keeps_the_safety_rules(self):
        arch = read(DESIGN_DIR / "ARCHITECTURE.md")
        for rule in ("pactl", "spaced-sound-helper", "i-was-clicked", "polkit",
                     "auth_admin", "run/user", "PipeWire", "pulseaudio --start",
                     "audio-card-profiles", "spaced-audio-restore"):
            self.assertIn(rule, arch)

    def test_architecture_never_writes_alsa_behind_the_server(self):
        # The sound server is the only writer: ALSA tools may appear in ARCHITECTURE.md
        # only inside the paragraph that rules them out.
        arch = read(DESIGN_DIR / "ARCHITECTURE.md")
        forbidden = ("amixer", "asoundrc", "alsactl", "wpctl")
        for para in arch.split("\n\n"):
            hits = [f for f in forbidden if f in para]
            if hits:
                low = para.lower()
                self.assertTrue("never" in low and "only writer" in low,
                                f"ALSA tool used as an action: {para[:120]!r}")
        self.assertIn("is the only writer", arch)


class MockupTests(unittest.TestCase):
    def test_every_page_rendered_in_both_themes(self):
        screens = DESIGN_DIR / "screens"
        for page in PAGES:
            for theme in ("spaced-dark", "light"):
                png = screens / f"{page}-{theme}.png"
                self.assertTrue(png.is_file(), f"{png} missing")
                with png.open("rb") as fh:
                    self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n", f"{png.name} is not a PNG")

    def test_prototype_is_fake_data_only_and_never_touches_audio(self):
        src = read(DESIGN_DIR / "prototype/sound_manager_prototype.py")
        # the test-sound path refuses without a click flag
        self.assertIn('"--i-was-clicked" not in sys.argv', src)
        self.assertNotIn("parecord", src)
        self.assertNotIn("Pulse(", src)
        self.assertIn("FAKE DATA ONLY", src.splitlines()[1])

    def test_prototype_carries_the_design_strings_and_tokens(self):
        src = read(DESIGN_DIR / "prototype/sound_manager_prototype.py")
        for s in ("LG monitor (HDMI on RTX 4070 Ti SUPER)",
                  "TCL TV (HDMI on RTX 4070 Ti SUPER)",
                  "Blue Yeti microphone (USB)", "Galyimage webcam microphone",
                  "Headphones (onboard audio, green jack)",
                  "Make this the one apps use", "Make this the one apps record from",
                  "Show my microphone level", "Move to…", "Open the old Sound Preferences"):
            self.assertIn(s, src)
        for token in ("level_start", "level_mid", "level_peak", "meter_track"):
            self.assertIn(token, src)

    def test_render_script_uses_the_shipped_themes_and_xvfb(self):
        sh = read(DESIGN_DIR / "prototype/render-screens.sh")
        self.assertIn("xvfb-run", sh)
        self.assertIn("Spaced-Dark", sh)
        self.assertIn("Spaced-Linux-Light", sh)
        self.assertIn("overlays/usr/share", sh)
        self.assertNotIn("paplay", sh)

    def test_design_does_not_promise_measurements_it_did_not_take(self):
        design = read(DESIGN_DIR / "DESIGN.md")
        self.assertNotIn("always faster", design)
        self.assertIsNone(re.search(r"\b\d+ ms (of )?(latency|delay) saved", design))


if __name__ == "__main__":
    unittest.main()
