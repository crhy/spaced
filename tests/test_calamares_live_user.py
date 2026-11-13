"""Removing the live account must never delete a separately mounted /home."""

from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "overlays/etc/calamares/modules/shellprocess@spaced-remove-live-user.conf"

FAKES = {
    "id": """#!/bin/sh
printf 'id %s\\n' "$*" >> "$SPACED_CALL_LOG"
exit "$SPACED_ID_EXIT"
""",
    "userdel": """#!/bin/sh
printf 'userdel %s\\n' "$*" >> "$SPACED_CALL_LOG"
""",
    "stat": """#!/bin/sh
path=
for argument in "$@"; do path="$argument"; done
case "$path" in
    /) printf '%s\\n' "$SPACED_ROOT_DEVICE" ;;
    /home) printf '%s\\n' "$SPACED_HOME_DEVICE" ;;
    *) printf 'stat: cannot stat %s\\n' "$path" >&2; exit 1 ;;
esac
""",
}


def userdel_line():
    """The single script line that removes the live account."""
    script = yaml.safe_load(CONF.read_text(encoding="utf-8"))["script"]
    lines = [line for line in script if "userdel" in line]
    if len(lines) != 1:
        raise AssertionError(f"expected one userdel script line, found {lines!r}")
    return lines[0]


class LiveUserRemovalTests(unittest.TestCase):
    def run_line(self, line, root_device="2049", home_device="2049", user_exists=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        fake_bin = Path(temp.name) / "bin"
        fake_bin.mkdir()
        log = Path(temp.name) / "calls.log"
        log.write_text("")
        for name, body in FAKES.items():
            fake = fake_bin / name
            fake.write_text(body, encoding="utf-8")
            fake.chmod(0o755)
        env = {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "SPACED_CALL_LOG": str(log),
            "SPACED_ID_EXIT": "0" if user_exists else "1",
            "SPACED_ROOT_DEVICE": root_device,
            "SPACED_HOME_DEVICE": home_device,
        }
        result = subprocess.run(["/bin/bash", "-c", line], env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return log.read_text(encoding="utf-8").splitlines()

    def test_home_on_root_filesystem_is_removed(self):
        calls = self.run_line(userdel_line(), root_device="2049", home_device="2049")
        self.assertIn("userdel -r user", calls)

    def test_home_on_separate_filesystem_is_kept(self):
        calls = self.run_line(userdel_line(), root_device="2049", home_device="2050")
        self.assertIn("userdel user", calls)
        self.assertFalse([call for call in calls if call.startswith("userdel") and "-r" in call])

    def test_absent_live_account_is_not_touched(self):
        calls = self.run_line(userdel_line(), user_exists=False)
        self.assertFalse([call for call in calls if call.startswith("userdel")])


if __name__ == "__main__":
    unittest.main()
