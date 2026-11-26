"""Tests for the document-portal FUSE mount guard (crhy/spaced#436).

The guard must: do nothing while the mount is present; restart only this user's
xdg-document-portal over D-Bus when it is missing (and log it); back off after
three restarts inside the window; never target another user's process; and be
free of the init system this distribution deliberately avoids.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "overlays" / "usr" / "lib" / "spaced-linux" / "spaced-portal-guard"


class PortalGuardTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="portal-guard-")
        self.runtime = Path(self.tmp) / "run"
        self.runtime.mkdir()
        self.bindir = Path(self.tmp) / "bin"
        self.bindir.mkdir()
        self.pkill_log = Path(self.tmp) / "pkill.log"
        self.gdbus_log = Path(self.tmp) / "gdbus.log"
        self.mounts = Path(self.tmp) / "mounts"
        self.guard_log = Path(self.tmp) / "state" / "portal-guard.log"

        # Fake pkill/gdbus that record their argv and always succeed.
        pkill = self.bindir / "pkill"
        pkill.write_text(
            "#!/bin/sh\nprintf '%%s\\n' \"$@\" >>'%s'\nexit 0\n" % self.pkill_log)
        gdbus = self.bindir / "gdbus"
        gdbus.write_text(
            "#!/bin/sh\nprintf '%%s\\n' \"$@\" >>'%s'\nexit 0\n" % self.gdbus_log)
        pkill.chmod(0o755)
        gdbus.chmod(0o755)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mounted(self):
        self.mounts.write_text(
            "sysfs /sys sysfs rw 0 0\n"
            "fuse.portal %s/doc fuse.portal rw,nosuid,nodev,relatime 0 0\n" % self.runtime)

    def _missing(self):
        self.mounts.write_text(
            "sysfs /sys sysfs rw 0 0\n"
            "tmpfs %s tmpfs rw,nosuid,nodev 0 0\n" % self.runtime)

    def _run(self, now):
        env = dict(os.environ)
        env.update({
            "XDG_RUNTIME_DIR": str(self.runtime),
            "SPACED_PROC_MOUNTS": str(self.mounts),
            "SPACED_PORTAL_LOG": str(self.guard_log),
            "SPACED_PORTAL_STATE": str(self.runtime / "spaced-portal-guard.state"),
            "SPACED_PORTAL_GUARD_ONCE": "1",
            "SPACED_PORTAL_NOW": str(now),
            "HOME": self.tmp,
            "PATH": str(self.bindir) + os.pathsep + env["PATH"],
        })
        return subprocess.run(["bash", str(GUARD)], env=env,
                              capture_output=True, text=True, timeout=30)

    def _log_text(self):
        return self.guard_log.read_text() if self.guard_log.exists() else ""

    def test_mounted_does_nothing(self):
        self._mounted()
        self._run(1_000_000)
        self.assertFalse(self.pkill_log.exists(),
                         "guard killed a portal while the mount was present")
        self.assertFalse(self.gdbus_log.exists(),
                         "guard re-activated the portal while the mount was present")
        self.assertNotIn("restarted", self._log_text())

    def test_missing_restarts_once_and_logs(self):
        self._missing()
        self._run(1_000_000)
        pk = self.pkill_log.read_text().split() if self.pkill_log.exists() else []
        self.assertIn("-u", pk, "pkill must be scoped to a user")
        # Re-activation happens over the session bus.
        gd = self.gdbus_log.read_text() if self.gdbus_log.exists() else ""
        self.assertIn("--session", gd.split())
        self.assertIn("org.freedesktop.portal.Documents.GetMountPoint", gd)
        self.assertIn("restarted xdg-document-portal", self._log_text())

    def test_backs_off_after_three(self):
        self._missing()
        # A fixed clock keeps all restarts inside one backoff window.
        for i in range(3):
            self._run(1_000_000 + i)
        self.pkill_log.unlink(missing_ok=True)
        self.gdbus_log.unlink(missing_ok=True)
        self._run(1_000_003)
        self.assertFalse(self.pkill_log.exists(),
                         "guard restarted beyond the three-restart budget")
        self.assertFalse(self.gdbus_log.exists(),
                         "guard re-activated beyond the three-restart budget")
        self.assertIn("backing off", self._log_text())

    def test_only_targets_this_user(self):
        self._missing()
        self._run(1_000_000)
        uid = str(os.getuid())
        pk = self.pkill_log.read_text().split() if self.pkill_log.exists() else []
        self.assertIn("-u", pk)
        self.assertEqual(pk[pk.index("-u") + 1], uid,
                         "guard must restrict the kill to the current user")

    def test_contains_no_init_system_reference(self):
        text = GUARD.read_text(encoding="utf-8")
        for token in ("systemctl", "systemd"):
            self.assertNotIn(token, text,
                             "the guard must not name the avoided init system")


if __name__ == "__main__":
    unittest.main()
