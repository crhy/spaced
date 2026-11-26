"""Release evidence checks for public-ISO upgrades through candidate APT."""
from hashlib import sha256
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/vm/qemu/published-upgrade-network-gate.sh"
VERIFY = ROOT / "scripts/tests/verify-published-upgrade-evidence.sh"
SINGLE_PACKAGE_PUBLISH = ROOT / "scripts/publish-apt-package.sh"
MAKEFILE = ROOT / "Makefile"


class PublishedUpgradeNetworkGateTests(unittest.TestCase):
    def test_scripts_parse(self):
        for script in (GATE, VERIFY, SINGLE_PACKAGE_PUBLISH):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    ["bash", "-n", str(script)], capture_output=True, text=True,
                    timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_gate_fetches_and_verifies_a_named_public_release(self):
        text = GATE.read_text(encoding="utf-8")
        self.assertIn('BASE_VERSION=${SPACED_UPGRADE_BASE_VERSION:-$VERSION}', text)
        self.assertIn('gh release download "v$BASE_VERSION"', text)
        self.assertIn('--pattern "$ISO_NAME.sha256"', text)
        self.assertIn('sha256sum -c', text)
        self.assertIn('[ "${PUBLIC_ISO##*/}" = "$ISO_NAME" ]', text)

    def test_gate_invalidates_old_evidence_then_runs_both_real_gates(self):
        text = GATE.read_text(encoding="utf-8")
        remove = text.index('rm -f "$EVIDENCE"')
        upgrade = text.index('"$SCRIPT_DIR/upgrade-test.sh"')
        network = text.index('"$SCRIPT_DIR/network-services-gate.sh"')
        evidence = text.index('cat > "$TEMP_EVIDENCE"')
        atomic_move = text.index('mv "$TEMP_EVIDENCE" "$EVIDENCE"')
        self.assertLess(remove, upgrade)
        self.assertLess(upgrade, network)
        self.assertLess(network, evidence)
        self.assertLess(evidence, atomic_move)
        self.assertIn('packages_sha256=$PACKAGES_SHA256', text)
        self.assertIn('base_version=$BASE_VERSION', text)

    def make_fixture(self, directory):
        repo = Path(directory) / "repo"
        packages = repo / "dists/spaced/main/binary-amd64/Packages"
        packages.parent.mkdir(parents=True)
        packages.write_text("Package: spaced-meta\nVersion: 11.26.3-2\n\n",
                            encoding="utf-8")
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        evidence = Path(directory) / "PASS.env"
        evidence.write_text(
            "result=PASS\n"
            f"version={version}\n"
            "base_version=11.26.3\n"
            "iso_name=spaced-linux-11.26.3-amd64.iso\n"
            f"iso_sha256={'0' * 64}\n"
            f"packages_sha256={sha256(packages.read_bytes()).hexdigest()}\n"
            "repository_suite=spaced\n"
            "completed_at=2026-11-25T12:00:00Z\n",
            encoding="utf-8")
        return repo, packages, evidence

    def run_verifier(self, repo, evidence):
        return subprocess.run(
            ["bash", str(VERIFY), str(repo), str(evidence)],
            capture_output=True, text=True, timeout=30)

    def test_verifier_accepts_matching_exact_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _packages, evidence = self.make_fixture(directory)
            result = self.run_verifier(repo, evidence)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("evidence matches candidate Packages", result.stdout)

    def test_verifier_rejects_a_changed_candidate_index(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, packages, evidence = self.make_fixture(directory)
            packages.write_text(packages.read_text(encoding="utf-8") + "# changed\n",
                                encoding="utf-8")
            result = self.run_verifier(repo, evidence)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Packages changed", result.stderr)

    def test_verifier_rejects_wrong_public_iso_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, _packages, evidence = self.make_fixture(directory)
            text = evidence.read_text(encoding="utf-8").replace(
                "iso_name=spaced-linux-11.26.3-amd64.iso",
                "iso_name=spaced-linux-11.26.2-amd64.iso")
            evidence.write_text(text, encoding="utf-8")
            result = self.run_verifier(repo, evidence)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("wrong public ISO", result.stderr)

    def test_publication_verifies_evidence_immediately_before_commit(self):
        text = MAKEFILE.read_text(encoding="utf-8")
        publish = text.split("apt-repo-publish:", 1)[1]
        verify = publish.index("verify-published-upgrade-evidence.sh")
        commit = publish.index("git add -A")
        push = publish.index("git push")
        self.assertLess(verify, commit)
        self.assertLess(commit, push)
        self.assertIn("published-upgrade-network-gate: apt-repo", text)
        self.assertIn('SPACED_UPGRADE_BASE_VERSION="$(UPGRADE_BASE_VERSION)"', text)

    def test_single_package_route_cannot_recommend_bypassing_the_gate(self):
        text = SINGLE_PACKAGE_PUBLISH.read_text(encoding="utf-8")
        warning = text.index("Do not push this candidate yet.")
        gate = text.index("published-upgrade-network-gate.sh", warning)
        verify = text.index("verify-published-upgrade-evidence.sh", gate)
        push = text.index("git push", verify)
        self.assertLess(warning, gate)
        self.assertLess(gate, verify)
        self.assertLess(verify, push)
        self.assertNotIn("Push immediately", text)


if __name__ == "__main__":
    unittest.main()
