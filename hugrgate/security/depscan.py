"""Dependency security scan. Slice 403.

Scans requirement specifiers (and optionally installed versions)
for three classes of findings:

- **advisories** — a curated, locally-maintained DB of verified CVEs
  (every entry was cross-checked against NVD/GitHub advisories; the
  DB is explicitly a *subset*, not a replacement for ``pip-audit`` /
  OSV — see :data:`ADVISORY_DB_NOTE`);
- **pinning** — unpinned or open-ended requirements that let a
  future malicious release slide in;
- **url_dependencies** — git/URL installs that bypass index trust.

Version comparison is a small PEP-440-subset matcher (``== >= <= >
< !=`` with comma-AND); good enough for advisory range checks
without pulling in ``packaging``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import tomllib

__all__ = [
    "ADVISORIES",
    "ADVISORY_DB_NOTE",
    "Advisory",
    "Finding",
    "installed_versions",
    "parse_requirement",
    "render_report",
    "scan_project",
    "scan_requirements",
]

ADVISORY_DB_NOTE = (
    "Curated subset of verified CVEs affecting HugrGate's dependency "
    "footprint. It is a tripwire, not a feed: run pip-audit/OSV for "
    "full coverage."
)


@dataclass(frozen=True)
class Advisory:
    package: str  # distribution name, normalized lowercase
    cve: str
    summary: str
    affected: str  # version specifier, e.g. "<5.3.1" or ">=2.0.0,<2.0.5"
    fixed_in: str
    severity: str  # low | medium | high | critical


#: Verified against NVD / GitHub Security Advisories, 2026-10-09.
ADVISORIES: tuple[Advisory, ...] = (
    Advisory("pyyaml", "CVE-2020-1747",
             "Arbitrary code execution via full_load/FullLoader on "
             "untrusted YAML input.", "<5.3.1", "5.3.1", "critical"),
    Advisory("pyyaml", "CVE-2020-14343",
             "Arbitrary code execution via unsafe YAML deserialization.",
             "<5.4", "5.4", "critical"),
    Advisory("pyyaml", "CVE-2017-18342",
             "Arbitrary code execution via yaml.load() on untrusted data.",
             "<5.1", "5.1", "critical"),
    Advisory("starlette", "CVE-2024-47874",
             "Denial of service: unbounded multipart form-field buffering "
             "exhausts memory.", "<0.40.0", "0.40.0", "high"),
    Advisory("urllib3", "CVE-2023-43804",
             "Cookie header leaked to a different origin on HTTP redirect.",
             "<1.26.17", "1.26.17", "high"),
    Advisory("urllib3", "CVE-2023-43804",
             "Cookie header leaked to a different origin on HTTP redirect.",
             ">=2.0.0,<2.0.5", "2.0.5", "high"),
    Advisory("urllib3", "CVE-2021-33503",
             "Catastrophic backtracking (ReDoS) on crafted URL authority.",
             "<1.26.5", "1.26.5", "high"),
    Advisory("requests", "CVE-2023-32681",
             "Proxy-Authorization header leaked to destination server on "
             "HTTPS redirect.", ">=2.3.0,<2.31.0", "2.31.0", "medium"),
)


@dataclass
class Finding:
    kind: str  # advisory | unpinned | no_upper_bound | url_dependency
    package: str
    severity: str
    detail: str
    cve: str = ""
    fixed_in: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "package": self.package,
            "severity": self.severity,
            "detail": self.detail,
            "cve": self.cve,
            "fixed_in": self.fixed_in,
        }


# --- version specifier matching (PEP 440 subset) -----------------------------

_VERSION_PART = re.compile(r"(\d+|[a-zA-Z]+)")


def _version_key(version: str) -> tuple:
    parts: list = []
    for chunk in _VERSION_PART.findall(version):
        parts.append(int(chunk) if chunk.isdigit() else chunk)
    return tuple(parts)


def _compare(version: str, op: str, target: str) -> bool:
    key, want = _version_key(version), _version_key(target)
    if op == "==":
        return key == want
    if op == "!=":
        return key != want
    if op == ">=":
        return key >= want
    if op == "<=":
        return key <= want
    if op == ">":
        return key > want
    if op == "<":
        return key < want
    raise ValueError(f"unsupported operator {op!r}")


_SPEC_CLAUSE = re.compile(r"\s*(==|!=|>=|<=|>|<)\s*([^\s,;]+)")


def matches_spec(version: str, spec: str) -> bool:
    """True when ``version`` satisfies every comma-separated clause."""
    clauses = [c for c in spec.split(",") if c.strip()]
    if not clauses:
        return True
    for clause in clauses:
        m = _SPEC_CLAUSE.fullmatch(clause.strip())
        if not m:
            raise ValueError(f"unsupported specifier clause {clause!r}")
        if not _compare(version, m.group(1), m.group(2)):
            return False
    return True


# --- requirement parsing -------------------------------------------------------

_REQ_NAME = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+(?:\[[A-Za-z0-9_,.\-]+\])?)\s*(.*)$")


def parse_requirement(line: str) -> dict[str, str]:
    """Parse one requirement line into name/specifier/url parts."""
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "!")):
        return {}
    url = ""
    # PEP 508 direct references: name @ url
    if "@" in line and "://" in line:
        name_part, url = line.split("@", 1)
        line, url = name_part.strip(), url.strip()
    elif "://" in line.split(";")[0]:
        url = line
        line = ""
    name = ""
    spec = ""
    if line:
        m = _REQ_NAME.match(line)
        if not m:
            return {}
        name = re.sub(r"\[.*\]$", "", m.group(1)).lower().replace("_", "-")
        spec = m.group(2).split(";")[0].strip()
    return {"name": name, "spec": spec, "url": url}


def _floor_version(spec: str) -> str | None:
    """Lowest version the specifier admits, for advisory range checks."""
    m = re.search(r"==\s*([^\s,;]+)", spec)
    if m:
        return m.group(1)
    m = re.search(r">=\s*([^\s,;]+)", spec)
    if m:
        return m.group(1)
    return None


# --- scanning --------------------------------------------------------------------

def installed_versions() -> dict[str, str]:
    """Distribution name -> installed version (stdlib importlib.metadata)."""
    versions: dict[str, str] = {}
    for dist in metadata.distributions():
        name = (dist.metadata["Name"] or "").lower().replace("_", "-")
        if name:
            versions[name] = dist.version
    return versions


def scan_requirements(
    requirements: list[str],
    installed: dict[str, str] | None = None,
) -> list[Finding]:
    """Scan requirement lines; check advisories against pins or installs."""
    findings: list[Finding] = []
    for raw in requirements:
        parsed = parse_requirement(raw)
        if not parsed:
            continue
        name, spec, url = (parsed["name"], parsed["spec"], parsed["url"])
        if url:
            findings.append(Finding(
                "url_dependency", name or url, "medium",
                f"direct URL install bypasses index trust: {url}"))
            continue
        if not name:
            continue
        if not spec:
            findings.append(Finding(
                "unpinned", name, "medium",
                f"{name} has no version specifier; any future release, "
                "including a compromised one, satisfies it"))
        elif not re.search(r"(==|<=|<|~=)", spec):
            findings.append(Finding(
                "no_upper_bound", name, "low",
                f"{name}{spec} admits unbounded future versions; "
                "consider an upper bound or =="))
        # Advisory check: prefer the installed version (ground truth),
        # else the specifier floor (what the manifest admits).
        probe: str | None = None
        if installed and name in installed:
            probe = installed[name]
        else:
            probe = _floor_version(spec)
        if probe is None:
            continue
        for advisory in ADVISORIES:
            if advisory.package != name:
                continue
            try:
                vulnerable = matches_spec(probe, advisory.affected)
            except ValueError:
                continue
            if vulnerable:
                findings.append(Finding(
                    "advisory", name, advisory.severity,
                    f"{name} {probe} is in the affected range "
                    f"{advisory.affected}: {advisory.summary}",
                    cve=advisory.cve, fixed_in=advisory.fixed_in))
    # De-duplicate identical (package, cve) pairs from floor+installed.
    seen: set[tuple[str, str, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.kind, finding.package, finding.cve or finding.detail)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def scan_project(root: str | Path = ".") -> list[Finding]:
    """Scan ``pyproject.toml`` dependencies + optional-dependencies."""
    root = Path(root)
    with open(root / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]
    requirements: list[str] = list(project.get("dependencies", []))
    for extra_deps in project.get("optional-dependencies", {}).values():
        requirements.extend(extra_deps)
    return scan_requirements(requirements, installed_versions())


def render_report(findings: list[Finding]) -> str:
    """Markdown summary of scan findings."""
    lines = ["# Dependency security scan", "",
             f"Findings: {len(findings)}", ""]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for finding in sorted(findings,
                          key=lambda f: (order.get(f.severity, 4), f.package)):
        lines.append(f"- **[{finding.severity}]** `{finding.package}` "
                     f"({finding.kind}): {finding.detail}")
        if finding.cve:
            lines.append(f"  - {finding.cve}; fixed in {finding.fixed_in}")
    lines.append("")
    lines.append(f"_{ADVISORY_DB_NOTE}_")
    return "\n".join(lines)
