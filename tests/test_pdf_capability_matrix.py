"""Fixture-driven checks for scripts/pdf-capability-matrix.py (issue #304).

The live machine is replaced by fixture directories: ``<package>.policy``
files, ``.desktop`` files and a dpkg status stanza, so these cases pass on
any host and need no package-manager state. The repository side is real:
the fixtures point at the checked-out ``config/`` and ``overlays/`` trees.
"""

import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pdf-capability-matrix.py"
CONFIG = ROOT / "config/pdf-viewers.yaml"
PACKAGES = ROOT / "config/packages.yaml"
CANDIDATES = ("atril", "mupdf", "okular", "xpdf", "zathura", "pdfcraft")
AXES = (
    "printing",
    "forms",
    "accessibility",
    "search",
    "encrypted-files",
    "sandbox-update-provenance",
    "mime-integration",
)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def table(default_app, candidates, claims=None):
    lines = [f"default_app: {default_app}", "decision: pending", "candidates:"]
    for name in candidates:
        lines.extend(
            [
                f"  {name}:",
                f"    binary: {name}",
                f"    desktop: {name}.desktop",
                f"    package: {name}",
            ]
        )
        for axis in AXES:
            lines.append(f"    {axis}: {(claims or {}).get((name, axis), 'unknown')}")
    return "\n".join(lines) + "\n"


def row(output, candidate, axis):
    """Return the printed capability row for one candidate and axis."""
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == candidate and fields[1] == axis:
            return line
    return ""


class MatrixFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def run_matrix(self, *args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--policy-dir",
                str(self.root / "policy"),
                "--applications-dir",
                str(self.root / "applications"),
                "--dpkg-status",
                str(self.root / "dpkg/status"),
                "--repo-root",
                str(ROOT),
                "--config",
                str(self.root / "config/pdf-viewers.yaml"),
                *args,
            ],
            text=True,
            capture_output=True,
            timeout=120,
        )

    def make_config(self, default_app="atril", candidates=("atril", "pdfcraft"), claims=None):
        write(self.root / "config/pdf-viewers.yaml", table(default_app, candidates, claims))

    def installed_policy(self, package, version="1.0-1"):
        write(
            self.root / f"policy/{package}.policy",
            f"{package}:\n  Installed: {version}\n  Candidate: {version}\n"
            "  Version table:\n"
            f" *** {version} 500\n"
            f"        500 http://mirror.example.invalid/devuan/merged ceres/main amd64 Packages\n",
        )

    def not_packaged_policy(self, package):
        write(self.root / f"policy/{package}.policy", f"{package}:\n  Installed: (none)\n  Version table:\n")

    def test_policy_without_candidate_line_is_not_packaged(self):
        self.not_packaged_policy("pdfcraft")
        write(
            self.root / "applications/pdfcraft.desktop",
            "[Desktop Entry]\nType=Application\nName=Pdfcraft\n",
        )
        self.make_config(default_app="atril", candidates=("pdfcraft",))
        result = self.run_matrix()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        packaging = [line for line in result.stdout.splitlines() if line.startswith("pdfcraft ")]
        self.assertTrue(any("NOT-PACKAGED" in line for line in packaging), result.stdout)
        self.assertIn("no Candidate: line", result.stdout)
        for axis in AXES:
            line = row(result.stdout, "pdfcraft", axis)
            self.assertIn("NOT-PACKAGED", line, f"{axis}: {result.stdout}")

    def test_check_refuses_a_default_that_is_not_packaged(self):
        self.not_packaged_policy("pdfcraft")
        self.make_config(default_app="pdfcraft", candidates=("pdfcraft",))
        result = self.run_matrix("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL pdfcraft packaging NOT-PACKAGED", result.stderr)
        self.assertIn("no Candidate: line", result.stderr)

    def test_desktop_without_a_print_action_reports_no_printing_evidence(self):
        self.installed_policy("atril", "1.28.4-1")
        write(
            self.root / "applications/atril.desktop",
            "[Desktop Entry]\nType=Application\nName=Atril Document Viewer\n"
            "TryExec=atril\nExec=atril %U\nKeywords=MATE;document;viewer;pdf;\n"
            "MimeType=application/pdf;\n",
        )
        write(
            self.root / "dpkg/status",
            "Package: atril\nStatus: install ok installed\nVersion: 1.28.4-1\n"
            "Depends: libgtk-3-0t64, libmate-desktop-2-17t64\n",
        )
        self.make_config(default_app="atril", candidates=("atril",))
        result = self.run_matrix()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        printing = row(result.stdout, "atril", "printing")
        self.assertIn("NO-EVIDENCE", printing, result.stdout)
        mime = row(result.stdout, "atril", "mime-integration")
        self.assertIn("EVIDENCE", mime, result.stdout)
        self.assertIn("applications/atril.desktop:MimeType=application/pdf", mime)

    def test_print_action_and_pipeline_dependency_report_evidence(self):
        self.installed_policy("pdfcraft", "0.9-1")
        write(
            self.root / "applications/pdfcraft.desktop",
            "[Desktop Entry]\nType=Application\nName=Pdfcraft\nTryExec=pdfcraft\n"
            "Exec=pdfcraft --print %f\nMimeType=application/pdf;\n",
        )
        write(
            self.root / "dpkg/status",
            "Package: pdfcraft\nStatus: install ok installed\nVersion: 0.9-1\n"
            "Depends: libcups2t64 (= 2.4.20-3), cups-client (>= 2.4.20-3)\n",
        )
        self.make_config(default_app="atril", candidates=("pdfcraft",))
        result = self.run_matrix()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        printing = row(result.stdout, "pdfcraft", "printing")
        self.assertIn("EVIDENCE", printing, result.stdout)
        self.assertIn("applications/pdfcraft.desktop:Exec=pdfcraft --print %f", printing)
        self.assertIn("dpkg status pdfcraft: Depends contains cups-client", printing)

    def test_check_refuses_a_capability_claim_without_evidence(self):
        self.installed_policy("atril", "1.28.4-1")
        write(
            self.root / "applications/atril.desktop",
            "[Desktop Entry]\nType=Application\nTryExec=atril\nExec=atril %U\n"
            "MimeType=application/pdf;\n",
        )
        write(self.root / "dpkg/status", "Package: atril\nStatus: install ok installed\nVersion: 1.28.4-1\n")
        self.make_config(
            default_app="atril",
            candidates=("atril",),
            claims={("atril", "printing"): "evidence"},
        )
        result = self.run_matrix("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL atril printing NO-EVIDENCE - (config records evidence)", result.stderr)

    def test_check_passes_when_the_default_is_packaged_and_mime_backed(self):
        self.installed_policy("atril", "1.28.4-1")
        write(
            self.root / "applications/atril.desktop",
            "[Desktop Entry]\nType=Application\nTryExec=atril\nExec=atril %U\nMimeType=application/pdf;\n",
        )
        write(self.root / "dpkg/status", "Package: atril\nStatus: install ok installed\nVersion: 1.28.4-1\n")
        self.make_config(default_app="atril", candidates=("atril",))
        result = self.run_matrix("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("check: atril is packaged and MIME-backed", result.stdout)

    def test_missing_policy_fixture_is_reported_as_unresolved(self):
        self.make_config(default_app="atril", candidates=("atril",))
        result = self.run_matrix("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL atril packaging UNKNOWN", result.stderr)


class ReviewedTableTests(unittest.TestCase):
    def test_table_lists_exactly_the_six_candidates(self):
        reviewed = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(sorted(reviewed["candidates"]), sorted(CANDIDATES))

    def test_table_keeps_the_shipped_default_and_the_pending_decision(self):
        reviewed = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(reviewed["default_app"], "atril")
        self.assertEqual(reviewed["decision"], "pending")

    def test_every_axis_stays_unknown_until_evidence_is_printed(self):
        reviewed = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        for name, record in reviewed["candidates"].items():
            self.assertEqual(sorted(record), sorted((*("binary", "desktop", "package"), *AXES)), name)
            for axis in AXES:
                self.assertEqual(record[axis], "unknown", f"{name} {axis}")

    def test_shipped_default_agrees_with_config_packages_yaml(self):
        reviewed = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        text = PACKAGES.read_text(encoding="utf-8")
        self.assertIn(f"  - {reviewed['default_app']}\n", text)
        shipped = [line.strip()[1:].strip() for line in text.splitlines() if line.strip().startswith("- ")]
        self.assertIn(reviewed["candidates"][reviewed["default_app"]]["package"], shipped)

    def test_script_imports_only_the_standard_library(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertLessEqual(imported, {"argparse", "re", "subprocess", "sys", "pathlib"})


if __name__ == "__main__":
    unittest.main()
