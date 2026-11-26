#!/usr/bin/env python3
"""PDF viewer capability matrix for issue #304.

Every value this script prints is read from this machine's own metadata
(``apt-cache policy``, the dpkg status database, installed ``.desktop`` files)
or from this repository's reviewed ``config/`` tables. Nothing is fetched
from the network, no third-party module is imported, and no capability is
reported without the source that produced it.

Description prose is never treated as evidence: only packaging state,
dependency/keyword tokens, desktop-file keys and reviewed config lines count.

``--check`` is the honest gate: it exits 0 only when every candidate resolves
to a packaging state, the recorded ``default_app`` is packaged and carries
MIME evidence, and no capability axis is claimed in ``config/pdf-viewers.yaml``
without a source this run printed.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

AXES = (
    "printing",
    "forms",
    "accessibility",
    "search",
    "encrypted-files",
    "sandbox-update-provenance",
    "mime-integration",
)
PACKAGING_KEYS = ("binary", "desktop", "package")
CLAIM_VALUES = ("unknown", "no-evidence", "not-packaged", "evidence")

# Structured tokens only: dependency names, Keywords entries, Exec values.
TOKEN_PATTERNS = {
    "printing": re.compile(r"^(cups|cups[-_].*|lp[0-9]*|lpr|printer.*|foomatic.*|ghostscript)$"),
    "forms": re.compile(r"(^|[-_])forms?([-_].*)?$"),
    "accessibility": re.compile(r"(accessib|a11y|high[-_]contrast|screen[-_]reader|blind)"),
    "search": re.compile(r"(^|[-_])(search|pdftotext|text[-_]extract)([-_].*)?$"),
    "encrypted-files": re.compile(r"(^|[-_])(gpg|gnupg|openssl|crypto[-_].*|secrets?|nss)([-_].*)?$"),
}
STATUS_FIELDS = ("Pre-Depends", "Depends", "Recommends", "Suggests", "Provides")
DESKTOP_PROBE_KEYS = ("Keywords", "Exec", "TryExec", "Categories", "Actions")


def parse_table(text):
    """Parse the reviewed table: nested mappings with scalar leaves only."""
    root = {}
    stack = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if raw.startswith("\t"):
            raise ValueError(f"tab indentation in reviewed table: {raw!r}")
        key, separator, value = raw.strip().partition(":")
        if not separator:
            raise ValueError(f"table line is not 'key: value': {raw.strip()!r}")
        key = key.strip()
        value = value.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else root
        if value:
            parent[key] = value
        else:
            child = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def load_config(path):
    """Return (default_app, decision, records, problems) for the reviewed table."""
    table = parse_table(path.read_text(encoding="utf-8"))
    default_app = table.get("default_app")
    decision = table.get("decision")
    candidates = table.get("candidates")
    problems = []
    records = {}
    if not default_app:
        problems.append(f"{path}: default_app is missing")
    if not decision:
        problems.append(f"{path}: decision is missing")
    if not isinstance(candidates, dict) or not candidates:
        problems.append(f"{path}: candidates block is missing or empty")
    for name, entry in (candidates or {}).items():
        if not isinstance(entry, dict):
            problems.append(f"{path}: {name} is not a record")
            continue
        missing = [key for key in PACKAGING_KEYS if not entry.get(key)]
        missing += [axis for axis in AXES if axis not in entry]
        if missing:
            problems.append(f"{path}: {name} is missing {', '.join(missing)}")
        for axis in AXES:
            if entry.get(axis) not in CLAIM_VALUES:
                problems.append(
                    f"{path}: {name} {axis} value {entry.get(axis)!r} "
                    f"is not one of {', '.join(CLAIM_VALUES)}"
                )
        records[name] = {
            "binary": entry.get("binary") or name,
            "desktop": entry.get("desktop") or f"{name}.desktop",
            "package": entry.get("package") or name,
            "axes": {axis: entry.get(axis) for axis in AXES},
        }
    return default_app, decision, records, problems


def split_tokens(value):
    parts = []
    for chunk in re.split(r"[,;|]", value):
        parts.extend(chunk.split())
    return parts


def token_matches(pattern, tokens):
    for token in tokens:
        name = token.split("(")[0].strip().lower()
        if name and pattern.search(name):
            return token
    return None


def read_policy(package, policy_dir):
    """Return packaging state, version, origin and source from the machine's APT data."""
    if policy_dir:
        fixture = policy_dir / f"{package}.policy"
        label = f"apt-cache policy {package} ({fixture})"
        if not fixture.is_file():
            return {"state": "UNKNOWN", "version": "", "origin": "", "label": label,
                    "source": f"{fixture}: no policy fixture"}
        text = fixture.read_text(encoding="utf-8", errors="replace")
    else:
        try:
            result = subprocess.run(
                ["apt-cache", "policy", package],
                text=True,
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {"state": "UNKNOWN", "version": "", "origin": "", "label": f"apt-cache policy {package}",
                    "source": f"apt-cache policy {package}: {error}"}
        if result.returncode != 0:
            return {"state": "UNKNOWN", "version": "", "origin": "", "label": f"apt-cache policy {package}",
                    "source": f"apt-cache policy {package}: exit {result.returncode}"}
        text = result.stdout
        label = f"apt-cache policy {package}"
    if not text.strip():
        return {"state": "NOT-PACKAGED", "version": "", "origin": "", "label": label,
                "source": f"{label}: no output (no candidate in the configured sources)"}
    installed = candidate = origin = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Installed:"):
            installed = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Candidate:"):
            candidate = stripped.split(":", 1)[1].strip()
        else:
            match = re.match(r"^\s+\d+\s+(\S+)", line)
            if match and not origin:
                origin = match.group(1)
    if installed and installed != "(none)":
        return {"state": "INSTALLED", "version": installed, "origin": origin, "label": label,
                "source": f"{label}: Installed: {installed}"}
    if candidate and candidate != "(none)":
        return {"state": "CANDIDATE", "version": candidate, "origin": origin, "label": label,
                "source": f"{label}: Candidate: {candidate}"}
    if "Candidate:" not in text:
        return {"state": "NOT-PACKAGED", "version": "", "origin": origin, "label": label,
                "source": f"{label}: no Candidate: line"}
    return {"state": "NOT-PACKAGED", "version": "", "origin": origin, "label": label,
            "source": f"{label}: Candidate: (none)"}


def read_status(status_path):
    """Parse the dpkg status database into per-package field dictionaries."""
    stanzas = {}
    current = None
    if not status_path.is_file():
        return stanzas
    for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Package: "):
            current = {}
            stanzas[line[len("Package: "):].strip()] = current
            continue
        if current is None or not line:
            continue
        if line[0].isspace():
            continue  # a continuation line belongs to the previous field's value
        key, separator, value = line.partition(":")
        if separator:
            current[key.strip()] = value.strip()
    return stanzas


def read_desktop(path):
    entries = {}
    if not path.is_file():
        return entries
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if "[" in key:
            continue
        entries.setdefault(key, []).append(value.strip())
    return entries


def find_desktop(applications_dir, record, installed):
    """Prefer the reviewed file name; fall back to the file that launches it."""
    path = applications_dir / record["desktop"]
    if path.is_file() or not installed:
        return path
    for candidate in sorted(applications_dir.glob("*.desktop")):
        entries = read_desktop(candidate)
        for key in ("TryExec", "Exec"):
            for value in entries.get(key, []):
                if value.split() and Path(value.split()[0]).name == record["binary"]:
                    return candidate
    return path


def read_repo(repo_root):
    """What Spaced itself ships and associates, from the reviewed config."""
    packages_path = repo_root / "config/packages.yaml"
    packages_display = Path("config/packages.yaml")
    packages = []
    if packages_path.is_file():
        for line in packages_path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*-\s+\S", line):
                packages.append((line.strip()[1:].strip(), line.strip()))
    mimeapps = repo_root / "overlays/usr/share/applications/mimeapps.list"
    mimeapps_display = Path("overlays/usr/share/applications/mimeapps.list")
    pdf_lines = []
    if mimeapps.is_file():
        for number, line in enumerate(mimeapps.read_text(encoding="utf-8").splitlines(), start=1):
            if "application/pdf" in line:
                pdf_lines.append((mimeapps_display, number, line.strip()))
    artifacts = repo_root / "config/external-artifacts.conf"
    artifacts_display = Path("config/external-artifacts.conf")
    artifact_text = []
    if artifacts.is_file():
        artifact_text = artifacts.read_text(encoding="utf-8").splitlines()
    return {
        "packages_path": packages_display,
        "packages": packages,
        "mimeapps": mimeapps_display,
        "pdf_lines": pdf_lines,
        "artifacts": artifacts_display,
        "artifact_text": artifact_text,
    }


def shipped_line(facts, package):
    for name, line in facts["packages"]:
        if name == package:
            return line
    return None


def artifact_line(facts, name):
    for number, line in enumerate(facts["artifact_text"], start=1):
        if re.search(rf"(^|[^A-Za-z0-9]){re.escape(name.lower())}", line, re.IGNORECASE):
            return f"{facts['artifacts']}:{number}: {line.strip()}"
    return None


def axis_sources(record, axis, desktop_path, desktop, stanza, facts, policy):
    """Return the printed sources that back one axis for one candidate."""
    if axis == "printing":
        action = None
        for key, values in desktop.items():
            if not re.match(r"^(Exec|Actions|X-.*Print.*)$", key, re.IGNORECASE):
                continue
            for value in values:
                if "print" in value.lower():
                    action = f"{desktop_path}:{key}={value}"
                    break
            if action:
                break
        pipeline = None
        for field in STATUS_FIELDS:
            token = token_matches(TOKEN_PATTERNS["printing"], split_tokens(stanza.get(field, "")))
            if token:
                pipeline = f"dpkg status {record['package']}: {field} contains {token}"
                break
        if not pipeline:
            for name, line in facts["packages"]:
                if TOKEN_PATTERNS["printing"].match(name):
                    pipeline = f"{facts['packages_path']}: {line}"
                    break
        return [action, pipeline] if action and pipeline else []

    if axis == "mime-integration":
        sources = []
        for value in desktop.get("MimeType", []):
            if "application/pdf" in value:
                sources.append(f"{desktop_path}:MimeType=application/pdf")
        for path, number, line in facts["pdf_lines"]:
            if record["desktop"] in line:
                sources.append(f"{path}:{number}: {line}")
        return sources

    if axis == "sandbox-update-provenance":
        origin = policy["origin"]
        shipped = shipped_line(facts, record["package"])
        pinned = artifact_line(facts, record["binary"])
        if not origin or not (shipped or pinned):
            return []
        sources = [f"{policy['label']}: {origin}"]
        if shipped:
            sources.append(f"{facts['packages_path']}: {shipped}")
        else:
            sources.append(pinned)
        return sources

    pattern = TOKEN_PATTERNS.get(axis)
    if pattern is None:
        return []
    sources = []
    for key in DESKTOP_PROBE_KEYS:
        for value in desktop.get(key, []):
            token = token_matches(pattern, split_tokens(value))
            if token:
                sources.append(f"{desktop_path}:{key} contains {token}")
                break
    for key, values in desktop.items():
        if not key.startswith("X-"):
            continue
        for value in values:
            token = token_matches(pattern, split_tokens(f"{key} {value}"))
            if token:
                sources.append(f"{desktop_path}:{key} contains {token}")
                break
    for field in STATUS_FIELDS:
        token = token_matches(pattern, split_tokens(stanza.get(field, "")))
        if token:
            sources.append(f"dpkg status {record['package']}: {field} contains {token}")
    return sources


def gather(options):
    """Build packaging rows and capability rows for every reviewed candidate."""
    default_app, decision, records, config_problems = load_config(options.config)
    facts = read_repo(options.repo_root)
    status = read_status(options.dpkg_status)
    applications_dir = options.applications_dir
    packaging = []
    capability = []
    for name, record in records.items():
        policy = read_policy(record["package"], options.policy_dir)
        installed = policy["state"] == "INSTALLED"
        desktop_path = find_desktop(applications_dir, record, installed)
        desktop = read_desktop(desktop_path)
        stanza = status.get(record["package"], {})
        source = policy["source"]
        if stanza.get("Version"):
            source += f"; dpkg status {record['package']}: Version {stanza['Version']}"
        if stanza.get("Origin"):
            source += f"; dpkg status {record['package']}: Origin {stanza['Origin']}"
        packaging.append(
            {
                "candidate": name,
                "state": policy["state"],
                "version": policy["version"] or "-",
                "source": source,
                "origin": policy["origin"],
            }
        )
        for axis in AXES:
            if policy["state"] == "NOT-PACKAGED":
                capability.append(
                    {
                        "candidate": name,
                        "axis": axis,
                        "state": "NOT-PACKAGED",
                        "sources": [policy["source"]],
                    }
                )
                continue
            sources = axis_sources(record, axis, desktop_path, desktop, stanza, facts, policy)
            capability.append(
                {
                    "candidate": name,
                    "axis": axis,
                    "state": "EVIDENCE" if sources else "NO-EVIDENCE",
                    "sources": sources,
                }
            )
    return {
        "default_app": default_app,
        "decision": decision,
        "config_path": options.config,
        "config_problems": config_problems,
        "records": records,
        "packaging": packaging,
        "capability": capability,
    }


def format_rows(matrix):
    name_width = max([len(row["candidate"]) for row in matrix["packaging"]] or [1])
    lines = []
    lines.append("PACKAGING")
    for row in matrix["packaging"]:
        lines.append(
            f"{row['candidate']:<{name_width}}  "
            f"{row['state']:<14}  {row['version']:<18}  {row['source']}"
        )
    lines.append("")
    lines.append("CAPABILITY")
    for row in matrix["capability"]:
        source = "; ".join(row["sources"]) if row["sources"] else "-"
        lines.append(
            f"{row['candidate']:<{name_width}}  {row['axis']:<26}  "
            f"{row['state']:<12}  {source}"
        )
    return lines


def row_text(row):
    source = "; ".join(row["sources"]) if row["sources"] else "-"
    return f"{row['candidate']} {row['axis']} {row['state']} {source}"


def check(matrix):
    """Return the offending rows when the reviewed table outruns its evidence."""
    problems = list(matrix["config_problems"])
    if not matrix["records"]:
        return [f"{problem} (reviewed table)" for problem in problems] + ["no candidates to check"]
    default = matrix["records"].get(matrix["default_app"])
    packaging_by_name = {row["candidate"]: row for row in matrix["packaging"]}
    if default is None:
        problems.append(
            f"config default_app {matrix['default_app']} is not a candidate in {matrix['config_path']}"
        )
    for row in matrix["packaging"]:
        if row["state"] == "UNKNOWN":
            problems.append(
                f"{row['candidate']} packaging {row['state']} {row['version']} {row['source']}"
            )
    if default is not None:
        default_row = packaging_by_name.get(matrix["default_app"])
        if default_row and default_row["state"] not in ("INSTALLED", "CANDIDATE"):
            problems.append(
                f"{matrix['default_app']} packaging {default_row['state']} "
                f"{default_row['version']} {default_row['source']}"
            )
        mime_row = next(
            (
                row
                for row in matrix["capability"]
                if row["candidate"] == matrix["default_app"] and row["axis"] == "mime-integration"
            ),
            None,
        )
        if mime_row is None or mime_row["state"] != "EVIDENCE":
            problems.append(
                f"{matrix['default_app']} mime-integration "
                f"{mime_row['state'] if mime_row else 'MISSING'} "
                "the shipped default PDF application has no MIME evidence"
            )
    for row in matrix["capability"]:
        claim = matrix["records"][row["candidate"]]["axes"][row["axis"]]
        if claim == "unknown":
            continue
        if claim == "no-evidence" and row["state"] != "NO-EVIDENCE":
            problems.append(f"{row_text(row)} (config records no-evidence)")
        elif claim == "not-packaged" and row["state"] != "NOT-PACKAGED":
            problems.append(f"{row_text(row)} (config records not-packaged)")
        elif claim == "evidence" and row["state"] != "EVIDENCE":
            problems.append(f"{row_text(row)} (config records evidence)")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="PDF viewer capability matrix (issue #304): machine evidence only."
    )
    parser.add_argument("--policy-dir", type=Path, help="directory of <package>.policy fixtures")
    parser.add_argument("--applications-dir", type=Path, help="directory of installed .desktop files")
    parser.add_argument("--dpkg-status", type=Path, help="dpkg status database or fixture")
    parser.add_argument("--repo-root", type=Path, help="repository root holding config/ and overlays/")
    parser.add_argument("--config", type=Path, help="reviewed pdf viewer table")
    parser.add_argument("--check", action="store_true", help="gate the table against its evidence")
    options = parser.parse_args(argv)

    options.repo_root = options.repo_root or Path(__file__).resolve().parents[1]
    options.applications_dir = options.applications_dir or Path("/usr/share/applications")
    options.dpkg_status = options.dpkg_status or Path("/var/lib/dpkg/status")
    options.config = options.config or options.repo_root / "config/pdf-viewers.yaml"

    try:
        matrix = gather(options)
    except (OSError, ValueError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 2

    print("PDF viewer capability matrix (issue #304)")
    print(f"default_app: {matrix['default_app']}")
    print(f"decision: {matrix['decision']}")
    print("\n".join(format_rows(matrix)))
    if options.check:
        problems = check(matrix)
        if problems:
            for problem in problems:
                print(f"FAIL {problem}", file=sys.stderr)
            return 1
        print(
            f"check: {matrix['default_app']} is packaged and MIME-backed; "
            "no axis is claimed without a printed source"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
