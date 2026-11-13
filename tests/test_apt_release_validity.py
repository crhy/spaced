#!/usr/bin/env python3
"""The signed Spaced APT repository must expire when it stops being updated.

Audit finding a08-05: the generated ``Release`` carried no ``Valid-Until``, so a
frozen, replayed or unsynced copy of the archive was accepted forever.  Both
repository generators now pass ``APT::FTPArchive::Release::ValidTime`` derived
from ``SPACED_APT_VALID_DAYS`` (default 180 days).

These tests rebuild each script's own ``apt-ftparchive ... release .`` command
line and run it on an empty temporary tree, so no signing key, network, root or
display is needed.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "scripts" / "build-apt-repo.sh"
PUBLISH_SCRIPT = ROOT / "scripts" / "publish-apt-package.sh"
OPTION_PREFIX = "-o APT::FTPArchive::Release::"
DEFAULT_VALID_DAYS = 180
# A space, a backslash and a newline: the shell line continuation of the harness.
SHELL_CONTINUATION = " " + chr(92) + chr(10)


def release_options(script_text):
    """Every -o APT::FTPArchive::Release::... argument of the Release generator."""
    options = []
    for line in script_text.splitlines():
        if OPTION_PREFIX in line:
            options.append(line[line.index(OPTION_PREFIX):].rstrip().rstrip("\\").rstrip())
    return options


def valid_days_line(script_text):
    """The script's own SPACED_APT_VALID_DAYS resolution line."""
    match = re.search(r"^VALID_DAYS=\$\{SPACED_APT_VALID_DAYS:-(\d+)\}$", script_text, re.M)
    assert match, "the script does not resolve SPACED_APT_VALID_DAYS with a documented default"
    return match


def generate_release(script_text, valid_days=None):
    """Run the script's own Release generator on an empty repository tree."""
    options = release_options(script_text)
    harness = "\n".join([
        "set -euo pipefail",
        'DIST=spaced',
        'COMP=main',
        valid_days_line(script_text).group(0),
        'cd "$1"',
        SHELL_CONTINUATION.join(
            ["apt-ftparchive"] + [f"    {option}" for option in options]
            + ["    release . > Release"]),
    ])
    env = dict(os.environ)
    env.pop("SPACED_APT_VALID_DAYS", None)
    if valid_days is not None:
        env["SPACED_APT_VALID_DAYS"] = str(valid_days)
    with tempfile.TemporaryDirectory() as work:
        result = subprocess.run(
            ["bash", "-c", harness, "release-generator", work],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=120, check=False)
        assert result.returncode == 0, result.stderr
        release = (Path(work) / "Release").read_text(encoding="utf-8")
    fields = {}
    for name in ("Date", "Valid-Until"):
        match = re.search(rf"^{name}: (.+)$", release, re.M)
        fields[name] = match.group(1).strip() if match else None
    return fields


class AptReleaseValidityTests(unittest.TestCase):
    def test_both_scripts_generate_a_valid_until_field(self):
        for script in (BUILD_SCRIPT, PUBLISH_SCRIPT):
            options = release_options(script.read_text(encoding="utf-8"))
            self.assertTrue(options, f"{script} generates no Release metadata")
            self.assertIn(
                "-o APT::FTPArchive::Release::ValidTime=$((VALID_DAYS * 86400))",
                options,
                f"{script} publishes a Release that never expires")

    def test_both_scripts_share_the_same_release_generator(self):
        build = release_options(BUILD_SCRIPT.read_text(encoding="utf-8"))
        publish = release_options(PUBLISH_SCRIPT.read_text(encoding="utf-8"))
        self.assertEqual(build, publish,
                         "the two repository generators no longer describe the same archive")

    def test_validity_window_defaults_to_180_days(self):
        for script in (BUILD_SCRIPT, PUBLISH_SCRIPT):
            match = valid_days_line(script.read_text(encoding="utf-8"))
            self.assertEqual(int(match.group(1)), DEFAULT_VALID_DAYS,
                             f"{script} does not default to {DEFAULT_VALID_DAYS} days")

    def test_valid_days_must_be_a_positive_integer(self):
        for script in (BUILD_SCRIPT, PUBLISH_SCRIPT):
            self.assertRegex(
                script.read_text(encoding="utf-8"),
                r'\[\[ "\$VALID_DAYS" =~ \^\[1-9\]\[0-9\]\*\$ \]\]',
                f"{script} accepts a non-numeric SPACED_APT_VALID_DAYS")

    def test_invalid_valid_days_stops_the_scripts_before_any_work(self):
        for script in (BUILD_SCRIPT, PUBLISH_SCRIPT):
            for invalid in ("0", "-7", "abc", "180d", "1.5"):
                with tempfile.TemporaryDirectory() as work:
                    env = dict(os.environ, SPACED_APT_VALID_DAYS=invalid,
                               # An empty keyring keeps a script that skipped the
                               # check from reaching the signing or staging steps.
                               GNUPGHOME=work)
                    argv = ["bash", str(script)]
                    if script is BUILD_SCRIPT:
                        argv.append(str(Path(work) / "repo"))
                    else:
                        argv += [str(Path(work) / "pkg.deb"), str(Path(work) / "repo")]
                    result = subprocess.run(argv, cwd=ROOT, env=env, text=True,
                                            capture_output=True, timeout=120, check=False)
                label = f"{script.name} SPACED_APT_VALID_DAYS={invalid!r}"
                self.assertNotEqual(result.returncode, 0, f"{label} was accepted")
                self.assertIn("SPACED_APT_VALID_DAYS", result.stderr,
                              f"{label} failed for an unrelated reason: {result.stderr}")

    @unittest.skipUnless(shutil.which("apt-ftparchive"), "apt-ftparchive is not installed")
    def test_generated_release_expires_180_days_after_its_date(self):
        for script in (BUILD_SCRIPT, PUBLISH_SCRIPT):
            fields = generate_release(script.read_text(encoding="utf-8"))
            label = script.name
            self.assertIsNotNone(fields["Date"], f"{label} writes no Date")
            self.assertIsNotNone(
                fields["Valid-Until"],
                f"{label} publishes a Release without Valid-Until ({fields})")
            date = parsedate_to_datetime(fields["Date"])
            valid_until = parsedate_to_datetime(fields["Valid-Until"])
            self.assertGreater(valid_until, date, f"{label} expires before it is published")
            self.assertLessEqual(
                abs(valid_until - date - timedelta(days=DEFAULT_VALID_DAYS)),
                timedelta(seconds=120),
                f"{label} expires {valid_until - date} after Date, "
                f"expected {DEFAULT_VALID_DAYS} days")

    @unittest.skipUnless(shutil.which("apt-ftparchive"), "apt-ftparchive is not installed")
    def test_valid_days_override_is_honoured(self):
        for script in (BUILD_SCRIPT, PUBLISH_SCRIPT):
            fields = generate_release(script.read_text(encoding="utf-8"), valid_days=7)
            date = parsedate_to_datetime(fields["Date"])
            valid_until = parsedate_to_datetime(fields["Valid-Until"])
            self.assertLessEqual(
                abs(valid_until - date - timedelta(days=7)), timedelta(seconds=120),
                f"{script.name} ignores SPACED_APT_VALID_DAYS=7 ({fields})")


if __name__ == "__main__":
    unittest.main()
