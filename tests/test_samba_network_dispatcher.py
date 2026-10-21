import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "overlays/etc/NetworkManager/dispatcher.d/90-spaced-samba-ready"


class SambaNetworkDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rc_root = self.root / "etc"
        (self.rc_root / "rc2.d").mkdir(parents=True)
        self.state = self.root / "state"
        self.calls = self.root / "calls"
        self.state.write_text("stopped\n")
        self.init = self.root / "smbd"
        self.init.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$1\" >> {self.calls}\n"
            f"case \"$1\" in\n"
            f"  status) grep -qx running {self.state} ;;\n"
            f"  start) printf 'running\\n' > {self.state} ;;\n"
            f"esac\n"
        )
        self.init.chmod(0o755)
        self.env = os.environ | {
            "SPACED_SMBD_INIT": str(self.init),
            "SPACED_RC_ROOT": str(self.rc_root),
            "SPACED_SAMBA_LOCK": str(self.root / "lock"),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def enable(self):
        (self.rc_root / "rc2.d/S06smbd").symlink_to(self.init)

    def run_dispatcher(self, action="up"):
        return subprocess.run(
            [str(DISPATCHER), "wlan0", action], env=self.env,
            text=True, capture_output=True, check=False,
        )

    def recorded_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_ignores_events_before_interface_is_ready(self):
        self.enable()
        self.assertEqual(self.run_dispatcher("down").returncode, 0)
        self.assertEqual(self.recorded_calls(), [])

    def test_respects_disabled_samba_service(self):
        self.assertEqual(self.run_dispatcher().returncode, 0)
        self.assertEqual(self.recorded_calls(), [])

    def test_starts_enabled_samba_after_interface_is_ready(self):
        self.enable()
        self.assertEqual(self.run_dispatcher().returncode, 0)
        self.assertEqual(self.recorded_calls(), ["status", "start"])
        self.assertEqual(self.state.read_text().strip(), "running")

    def test_does_not_restart_running_samba(self):
        self.enable()
        self.state.write_text("running\n")
        self.assertEqual(self.run_dispatcher("dhcp4-change").returncode, 0)
        self.assertEqual(self.recorded_calls(), ["status"])


if __name__ == "__main__":
    unittest.main()
