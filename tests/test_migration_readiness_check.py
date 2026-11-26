"""Issue #417: read-only migration readiness checker (first slice).

The checker reports whether a system is a Devuan/Debian/Ubuntu derivative
Spaced can migrate from. These cases point the shipped tool at throwaway
--os-release and --root fixtures, so this machine's real /etc/os-release,
/proc, /usr/bin and package files are never consulted or changed.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "overlays/usr/lib/spaced-linux/spaced-migration-check"

OS_RELEASES = {
    "devuan": 'PRETTY_NAME="Devuan GNU/Linux 5 (chimaera)"\n'
              'NAME="Devuan"\nVERSION_ID="5.0"\nID=devuan\nID_LIKE=debian\n',
    "ubuntu": 'PRETTY_NAME="Ubuntu 24.04.1 LTS"\n'
              'NAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\nID_LIKE=debian\n',
    "spaced": 'PRETTY_NAME="Spaced Linux 11.26.3"\n'
              'NAME="Spaced Linux"\nVERSION_ID="11.26.3"\nID=spaced\nID_LIKE=debian\n',
    "gentoo": 'NAME="Gentoo"\nID=gentoo\nVERSION_ID="2.17"\n',
}


def make_fixture(case, distro, with_apt=True, with_init=True):
    root = case / distro / "root"
    (root / "etc").mkdir(parents=True)
    (root / "etc/os-release").write_text(OS_RELEASES[distro], encoding="utf-8")
    if with_init:
        (root / "proc/1").mkdir(parents=True)
        (root / "proc/1/comm").write_text("init\n", encoding="utf-8")
        (root / "etc/inittab").write_text("id:3:initdefault:\n", encoding="utf-8")
    if with_apt:
        (root / "usr/bin").mkdir(parents=True)
        for name in ("apt", "apt-get", "dpkg", "mate-session"):
            (root / "usr/bin" / name).write_text("", encoding="utf-8")
    return root


class MigrationReadinessTests(unittest.TestCase):
    def run_check(self, distro, with_apt=True, with_init=True):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            case = temp / distro
            root = make_fixture(case, distro, with_apt=with_apt, with_init=with_init)
            before = self.snapshot(temp)
            env = {key: value for key, value in os.environ.items()
                   if key not in ("DISPLAY", "XDG_CURRENT_DESKTOP")}
            result = subprocess.run(
                [sys.executable, str(TOOL),
                 "--os-release", str(root / "etc/os-release"), "--root", str(root)],
                cwd=str(case), env=env, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, self.snapshot(temp))
            return result.stdout

    @staticmethod
    def snapshot(temp):
        return sorted((str(path.relative_to(temp)), path.stat().st_mtime_ns)
                      for path in temp.rglob("*"))

    def test_devuan_fixture_is_migratable(self):
        report = self.run_check("devuan")
        self.assertIn("verdict: migratable", report)
        self.assertIn("distro: Devuan GNU/Linux 5 (chimaera) [id=devuan version=5.0]", report)
        self.assertIn("init: sysvinit (supported)", report)
        self.assertIn("packages: apt (apt/dpkg found)", report)

    def test_ubuntu_fixture_is_migratable(self):
        report = self.run_check("ubuntu")
        self.assertIn("verdict: migratable", report)
        self.assertIn("[id=ubuntu version=24.04]", report)
        self.assertIn("desktop: MATE", report)

    def test_spaced_fixture_is_already_spaced(self):
        report = self.run_check("spaced")
        self.assertIn("verdict: already-spaced", report)

    def test_unknown_id_fixture_is_not_supported(self):
        report = self.run_check("gentoo")
        self.assertIn("verdict: not-supported", report)
        self.assertIn("not a Devuan/Debian/Ubuntu derivative", report)

    def test_family_without_apt_is_not_supported(self):
        report = self.run_check("ubuntu", with_apt=False)
        self.assertIn("verdict: not-supported", report)


if __name__ == "__main__":
    unittest.main()
