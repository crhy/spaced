import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "overlays/etc/NetworkManager/dispatcher.d/90-spaced-samba-ready"


class SambaNetworkWsddRegressionTests(unittest.TestCase):
    """Offline slice of the 11.26.3 Windows-networking regression (#432).

    Mirrors the headless fixture pattern of test_samba_network_dispatcher.py:
    fake init scripts and SPACED_* env vars, no real network, no two machines.
    It asserts the bring-up ordering/robustness of the dispatcher, not the
    peer-visible SMB/WS-Discovery browse that has no offline repro.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rc_root = self.root / "etc"
        (self.rc_root / "rc2.d").mkdir(parents=True)
        self.calls = self.root / "calls"
        self.fd = self.root / "fd"
        self.smbd_state = self.root / "smbd.state"
        self.wsdd_state = self.root / "wsdd.state"
        self.smbd_state.write_text("stopped\n")
        self.wsdd_state.write_text("stopped\n")

        self.smbd = self._make_init("smbd", self.smbd_state)
        self.wsdd = self._make_init("wsdd", self.wsdd_state)

        self.env = os.environ | {
            "SPACED_SMBD_INIT": str(self.smbd),
            "SPACED_WSDD_INIT": str(self.wsdd),
            "SPACED_RC_ROOT": str(self.rc_root),
            "SPACED_SAMBA_LOCK": str(self.root / "lock"),
        }

    def _make_init(self, name, state):
        # On start the script records whether the dispatcher's flock descriptor
        # (fd 9) is still open here: it would be inherited by a backgrounded
        # daemon and keep the lock for its whole lifetime (AGENTS.md 7>&- rule).
        path = self.root / name
        path.write_text(
            "#!/bin/sh\n"
            f"printf '%s %s\\n' {name} \"$1\" >> {self.calls}\n"
            "if [ \"$1\" = start ]; then\n"
            "    if [ -e /proc/self/fd/9 ]; then\n"
            f"        printf '%s leaked\\n' {name} >> {self.fd}\n"
            "    else\n"
            f"        printf '%s closed\\n' {name} >> {self.fd}\n"
            "    fi\n"
            f"    printf 'running\\n' > {state}\n"
            "fi\n"
            "if [ \"$1\" = status ]; then\n"
            f"    grep -qx running {state}\n"
            "fi\n"
        )
        path.chmod(0o755)
        return path

    def tearDown(self):
        self.tmp.cleanup()

    def enable(self):
        (self.rc_root / "rc2.d/S06smbd").symlink_to(self.smbd)
        # 11.26.4: the dispatcher only starts spaced-wsdd when it is enabled at boot.
        (self.rc_root / "rc2.d/S07spaced-wsdd").symlink_to(self.wsdd)

    def run_dispatcher(self, action="up"):
        return subprocess.run(
            [str(DISPATCHER), "wlan0", action], env=self.env,
            text=True, capture_output=True, check=False,
        )

    def recorded(self, name):
        text = self.calls.read_text() if self.calls.exists() else ""
        return [
            parts[1] for parts in
            (line.split(None, 1) for line in text.splitlines())
            if len(parts) == 2 and parts[0] == name
        ]

    def fd_state(self):
        return self.fd.read_text().split() if self.fd.exists() else []

    def test_down_event_does_not_start_wsdd_or_smbd(self):
        self.enable()
        for action in ("down", "pre-down", "vpn-up"):
            self.assertEqual(self.run_dispatcher(action).returncode, 0)
        self.assertEqual(self.recorded("smbd"), [])
        self.assertEqual(self.recorded("wsdd"), [])

    def test_first_ready_up_starts_wsdd_once_after_smbd(self):
        self.enable()
        self.assertEqual(self.run_dispatcher("up").returncode, 0)
        # smbd is up first so shares answer (and is rechecked before anything is
        # advertised), then wsdd announces them.
        self.assertEqual(self.recorded("smbd"), ["status", "start", "status"])
        self.assertEqual(self.recorded("wsdd"), ["status", "start"])
        self.assertEqual(self.smbd_state.read_text().strip(), "running")
        self.assertEqual(self.wsdd_state.read_text().strip(), "running")

    def test_repeated_up_does_not_double_start_or_race(self):
        self.enable()
        self.assertEqual(self.run_dispatcher("up").returncode, 0)
        self.assertEqual(self.run_dispatcher("dhcp4-change").returncode, 0)
        # The second event sees both daemons already running and starts neither
        # (smbd: start check + pre-advertise check on each event).
        self.assertEqual(self.recorded("smbd"), ["status", "start", "status", "status", "status"])
        self.assertEqual(self.recorded("wsdd"), ["status", "start", "status"])
        self.assertEqual(self.smbd_state.read_text().strip(), "running")
        self.assertEqual(self.wsdd_state.read_text().strip(), "running")

    def test_started_daemons_do_not_hijack_the_flock(self):
        self.enable()
        self.assertEqual(self.run_dispatcher("up").returncode, 0)
        # AGENTS.md: a background process started under a flock must close the
        # lock descriptor, or it keeps the lock for its whole lifetime. Both
        # starts must have closed fd 9; neither may leak it.
        self.assertEqual(self.fd_state(), ["smbd", "closed", "wsdd", "closed"])

    def test_disabled_wsdd_is_not_started(self):
        (self.rc_root / "rc2.d/S06smbd").symlink_to(self.smbd)
        self.assertEqual(self.run_dispatcher("up").returncode, 0)
        self.assertEqual(self.recorded("wsdd"), [])


if __name__ == "__main__":
    unittest.main()
