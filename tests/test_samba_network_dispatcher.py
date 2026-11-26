import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "overlays/etc/NetworkManager/dispatcher.d/90-spaced-samba-ready"


class SambaNetworkDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rc_root = self.root / "etc"
        (self.rc_root / "rc2.d").mkdir(parents=True)
        self.state = self.root / "smbd-state"
        self.wsdd_state = self.root / "wsdd-state"
        self.calls = self.root / "calls"
        self.state.write_text("stopped\n")
        self.wsdd_state.write_text("stopped\n")
        self.init = self.make_init("smbd", self.state)
        self.wsdd_init = self.make_init("spaced-wsdd", self.wsdd_state)
        self.env = os.environ | {
            "SPACED_SMBD_INIT": str(self.init),
            "SPACED_WSDD_INIT": str(self.wsdd_init),
            "SPACED_RC_ROOT": str(self.rc_root),
            "SPACED_SAMBA_LOCK": str(self.root / "lock"),
        }

    def make_init(self, name, state):
        init = self.root / name
        init.write_text(
            "#!/bin/sh\n"
            f"printf '{name} %s\\n' \"$1\" >> {self.calls}\n"
            f"case \"$1\" in\n"
            f"  status) grep -qx running {state} ;;\n"
            f"  start) printf 'running\\n' > {state} ;;\n"
            f"esac\n"
        )
        init.chmod(0o755)
        return init

    def tearDown(self):
        self.tmp.cleanup()

    def enable_smbd(self):
        (self.rc_root / "rc2.d/S06smbd").symlink_to(self.init)

    def enable_wsdd(self):
        (self.rc_root / "rc2.d/S07spaced-wsdd").symlink_to(self.wsdd_init)

    def enable_services(self):
        self.enable_smbd()
        self.enable_wsdd()

    def run_dispatcher(self, action="up"):
        return subprocess.run(
            [str(DISPATCHER), "wlan0", action], env=self.env,
            text=True, capture_output=True, check=False,
        )

    def recorded_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_ignores_events_before_interface_is_ready(self):
        self.enable_services()
        self.assertEqual(self.run_dispatcher("down").returncode, 0)
        self.assertEqual(self.recorded_calls(), [])

    def test_respects_disabled_samba_service(self):
        self.assertEqual(self.run_dispatcher().returncode, 0)
        self.assertEqual(self.recorded_calls(), [])

    def test_starts_enabled_samba_after_interface_is_ready(self):
        self.enable_services()
        self.assertEqual(self.run_dispatcher().returncode, 0)
        self.assertEqual(self.recorded_calls(), [
            "smbd status", "smbd start", "smbd status",
            "spaced-wsdd status", "spaced-wsdd start",
        ])
        self.assertEqual(self.state.read_text().strip(), "running")
        self.assertEqual(self.wsdd_state.read_text().strip(), "running")

    def test_recovers_wsdd_without_restarting_running_samba(self):
        self.enable_services()
        self.state.write_text("running\n")
        self.assertEqual(self.run_dispatcher("dhcp4-change").returncode, 0)
        self.assertEqual(self.recorded_calls(), [
            "smbd status", "smbd status", "spaced-wsdd status",
            "spaced-wsdd start",
        ])

    def test_respects_disabled_wsdd_service(self):
        self.enable_smbd()
        self.state.write_text("running\n")
        self.assertEqual(self.run_dispatcher().returncode, 0)
        self.assertEqual(self.recorded_calls(), ["smbd status", "smbd status"])

    def test_does_not_advertise_a_failed_samba_server(self):
        self.enable_services()
        self.init.write_text(
            "#!/bin/sh\n"
            f"printf 'smbd %s\\n' \"$1\" >> {self.calls}\n"
            f"case \"$1\" in status) exit 1 ;; start) exit 0 ;; esac\n"
        )
        self.init.chmod(0o755)
        self.assertEqual(self.run_dispatcher().returncode, 0)
        self.assertEqual(self.recorded_calls(), [
            "smbd status", "smbd start", "smbd status",
        ])

    def test_started_daemon_does_not_inherit_dispatcher_lock(self):
        self.enable_smbd()
        released = self.root / "lock-released"
        lock = self.root / "lock"
        self.init.write_text(
            "#!/bin/sh\n"
            f"case \"$1\" in\n"
            f"  status) grep -qx running {self.state} ;;\n"
            f"  start) printf 'running\\n' > {self.state}; "
            f"(sleep 0.05; flock -n {lock} -c 'touch {released}') & ;;\n"
            f"esac\n"
        )
        self.init.chmod(0o755)
        self.assertEqual(self.run_dispatcher().returncode, 0)
        for _ in range(50):
            if released.exists():
                break
            time.sleep(0.02)
        self.assertTrue(released.exists(), "child inherited and retained lock fd 9")


if __name__ == "__main__":
    unittest.main()
