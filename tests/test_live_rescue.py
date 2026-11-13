"""The live USB is also a rescue system, and its passwords must be obvious.

rhY keeps live root login on purpose; what has to change is that the user can
find the passwords and the recovery tools.  This test reads the real image hook
and the real generated package list, and derives the passwords from the
`chpasswd` lines instead of repeating them here.
"""
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_LIST = ROOT / "scripts" / "iso" / "package-list.sh"
LIVE_HOOK = ROOT / "scripts" / "iso" / "01-configure.chroot"
SKEL = ROOT / "overlays" / "etc" / "skel"

PASSWORD_FILE = "Live session passwords.txt"

# Every recovery tool the live image must carry (audit f22 step 2).
RESCUE_TOOLS = (
    "gparted", "testdisk", "gddrescue", "smartmontools", "efibootmgr", "ntfs-3g",
    "dosfstools", "exfatprogs", "cryptsetup", "lvm2", "rsync", "parted",
)


def generated_packages():
    result = subprocess.run(
        ["bash", str(PACKAGE_LIST)],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def chpasswd_password(account):
    """The password 01-configure.chroot sets for `account` with chpasswd."""
    match = re.search(
        rf'echo "{account}:([^"]+)" \| chpasswd',
        LIVE_HOOK.read_text(encoding="utf-8"),
    )
    if not match:
        raise AssertionError(f"01-configure.chroot sets no {account} password with chpasswd")
    return match.group(1)


def password_file_writer():
    """The line that creates the live Desktop note, or None."""
    for line in LIVE_HOOK.read_text(encoding="utf-8").splitlines():
        if PASSWORD_FILE in line and not line.lstrip().startswith("#"):
            return line
    return None


def password_file_text():
    """The heredoc body 01-configure.chroot writes to the live Desktop."""
    writer = password_file_writer()
    if writer is None:
        raise AssertionError(f"01-configure.chroot never writes {PASSWORD_FILE}")
    marker = re.search(r"<<'([A-Za-z_]+)'", writer)
    if not marker:
        raise AssertionError(f"{PASSWORD_FILE} is not written from a quoted heredoc")
    terminator = marker.group(1)
    lines = LIVE_HOOK.read_text(encoding="utf-8").splitlines()
    body = []
    for line in lines[lines.index(writer) + 1:]:
        if line == terminator:
            return "\n".join(body)
        body.append(line)
    raise AssertionError(f"unterminated {PASSWORD_FILE} heredoc in 01-configure.chroot")


class LiveRescueTests(unittest.TestCase):
    def test_rescue_tools_are_in_the_image_package_list(self):
        packages = generated_packages()
        self.assertTrue(packages, "scripts/iso/package-list.sh produced no packages")
        missing = sorted(set(RESCUE_TOOLS) - packages)
        self.assertEqual(missing, [], "the live image ships no rescue tool named: "
                                      + ", ".join(missing))

    def test_smartmontools_daemon_is_disabled_but_stays_installed(self):
        script = LIVE_HOOK.read_text(encoding="utf-8")
        self.assertIn("update-rc.d smartmontools disable", script)

    def test_live_desktop_note_carries_the_real_passwords(self):
        text = password_file_text()
        root_password = chpasswd_password("root")
        live_user_password = chpasswd_password("user")
        self.assertIn(root_password, text,
                      f"the live note does not show the root password set by chpasswd")
        self.assertIn(live_user_password, text,
                      "the live note does not show the live user password set by chpasswd")
        self.assertIn("sudo", text, "the live note does not mention password-free sudo")
        self.assertIn("GParted", text, "the live note does not name the rescue tools")
        self.assertTrue(5 <= len(text.splitlines()) <= 8,
                        f"the live note must be 5-8 short lines, found {len(text.splitlines())}")

    def test_live_desktop_note_is_live_only(self):
        writer = password_file_writer()
        self.assertIsNotNone(writer, f"01-configure.chroot never writes {PASSWORD_FILE}")
        self.assertIn("/home/user/Desktop/", writer.replace('"', ""),
                      "the note is not written into the live user's Desktop")
        self.assertNotIn("/etc/skel", writer, "the note is written into /etc/skel")
        for path in SKEL.rglob("*"):
            if not path.is_file():
                continue
            self.assertNotIn(PASSWORD_FILE.encode(), path.read_bytes(),
                             f"{path.relative_to(ROOT)} would give an installed system the note")


if __name__ == "__main__":
    unittest.main()
