"""License/provenance audit (slice 497).

HugrGate 1.0 ships a dependency tree; the tree's licenses must be
known. This module inventories installed distributions via
``importlib.metadata``, normalizes their declared license into an
SPDX-ish token set, and classifies each package:

- ``allow`` — permissive license on the allowlist;
- ``review`` — copyleft (GPL/AGPL/LGPL family) or unknown: legal
  review required, surfaced loudly, never silently passed.

Compound ``License-Expression`` values (``A AND B``) are split and
each token classified; the package takes the strictest token
verdict. The repo itself is Apache-2.0 (pyproject.toml).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import distributions
from typing import Any

__all__ = [
    "ALLOWLIST",
    "LicenseReport",
    "PackageLicense",
    "audit_installed",
    "audit_runtime",
    "classify_license",
    "runtime_closure",
]

#: Permissive licenses cleared for the 1.0 dependency tree.
#:
#: MPL-2.0 rationale: weak, file-level copyleft; using the package
#: unmodified (the case for every dependency here) triggers no
#: source-disclosure duty, and it is explicitly compatible with
#: Apache-2.0 combination.
ALLOWLIST: frozenset[str] = frozenset({
    "MIT",
    "APACHE-2.0",
    "BSD-2-CLAUSE",
    "BSD-3-CLAUSE",
    "0BSD",
    "ISC",
    "PSF-2.0",
    "PSF",
    "PYTHON-2.0",
    "ZLIB",
    "UNLICENSE",
    "CC0-1.0",
    "BSL-1.0",
    "MPL-2.0",
})

#: Copyleft family: not auto-failed, but requires human legal review.
COPYLEFT_TOKENS: frozenset[str] = frozenset({
    "GPL-2.0", "GPL-3.0", "GPL-2.0-ONLY", "GPL-3.0-ONLY",
    "AGPL-3.0", "AGPL-1.0",
    "LGPL-2.0", "LGPL-2.1", "LGPL-3.0",
    "GPL", "AGPL", "LGPL",
})

_SPLIT_RE = re.compile(r"\s+(?:AND|OR|WITH)\s+", re.IGNORECASE)


def _normalize(text: str) -> list[str]:
    """Split a license declaration into candidate SPDX-ish tokens."""
    text = text.upper().replace("LICENCE", "LICENSE")
    parts = _SPLIT_RE.split(text)
    tokens: list[str] = []
    for part in parts:
        part = part.strip(" ()")
        # Strip common free-text wrappers: "License :: OSI Approved :: MIT"
        # or "MIT License".
        for token in list(ALLOWLIST | COPYLEFT_TOKENS):
            if token in part:
                tokens.append(token)
                break
        else:
            tokens.append(part)
    return tokens


def classify_license(declaration: str | None) -> str:
    """Classify a license declaration: allow | review | unknown."""
    if not declaration or not declaration.strip():
        return "unknown"
    tokens = _normalize(declaration)
    # Copyleft check first: "GPL" is a substring risk only if we
    # matched loosely — _normalize matches exact tokens, but a raw
    # "GPL-3.0" token must beat an "MIT" token in the same decl.
    if any(t in COPYLEFT_TOKENS for t in tokens):
        return "review"
    if tokens and all(t in ALLOWLIST for t in tokens):
        return "allow"
    return "unknown"


def _declaration(dist: Any) -> str | None:
    meta = dist.metadata
    return meta.get("License-Expression") or meta.get("License") or None


@dataclass
class PackageLicense:
    name: str
    version: str
    declaration: str | None
    status: str  # allow | review | unknown


@dataclass
class LicenseReport:
    packages: list[PackageLicense] = field(default_factory=list)

    @property
    def by_status(self) -> dict[str, list[PackageLicense]]:
        grouped: dict[str, list[PackageLicense]] = {}
        for pkg in self.packages:
            grouped.setdefault(pkg.status, []).append(pkg)
        return grouped

    @property
    def needs_review(self) -> list[PackageLicense]:
        return [p for p in self.packages if p.status != "allow"]

    @property
    def clean(self) -> bool:
        return not self.needs_review

    def to_dict(self) -> dict[str, Any]:
        return {
            "packages": [
                {"name": p.name, "version": p.version,
                 "license": p.declaration, "status": p.status}
                for p in sorted(self.packages, key=lambda p: p.name.lower())
            ],
            "summary": {s: len(v)
                        for s, v in self.by_status.items()},
            "clean": self.clean,
        }


def audit_installed() -> LicenseReport:
    """Inventory licenses of all installed distributions."""
    report = LicenseReport()
    seen: set[str] = set()
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        declaration = _declaration(dist)
        report.packages.append(PackageLicense(
            name=name,
            version=dist.version or "?",
            declaration=declaration,
            status=classify_license(declaration),
        ))
    return report


def _project_dependency_names(pyproject: str) -> list[str]:
    """Root runtime dependency names from pyproject (no tomllib needed).

    Parses the ``dependencies = [...]`` array with a regex so the
    audit also runs on Python 3.10 (no stdlib tomllib there).
    """
    from pathlib import Path

    text = Path(pyproject).read_text(encoding="utf-8")
    match = re.search(r"^dependencies\s*=\s*\[(.*?)\]",
                      text, re.DOTALL | re.MULTILINE)
    if not match:
        return []
    names = re.findall(r'"([A-Za-z0-9_.\-]+)', match.group(1))
    return names


def _requirement_name(requirement: str) -> str:
    """Strip version specs, markers, and extras from a requirement."""
    name = re.split(r"[<>=!~\s;\[]", requirement, maxsplit=1)[0]
    return name.strip().lower()


def runtime_closure(pyproject: str = "pyproject.toml") -> set[str]:
    """Installed distribution names in the runtime dependency closure.

    Roots come from ``pyproject.toml`` ``dependencies``; the closure
    follows each installed distribution's ``Requires-Dist`` (markers
    ignored — conservative over-approximation).
    """
    roots = {_requirement_name(n) for n in
             _project_dependency_names(pyproject)}
    index: dict[str, list[str]] = {}
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        reqs = dist.metadata.get_all("Requires-Dist") or []
        index[name.lower()] = [_requirement_name(r) for r in reqs]
    closure = set(roots)
    stack = list(roots)
    while stack:
        current = stack.pop()
        for child in index.get(current, []):
            if child and child not in closure:
                closure.add(child)
                stack.append(child)
    # Keep only names actually installed.
    return {n for n in closure if n in index}


def audit_runtime(pyproject: str = "pyproject.toml",
                  project_name: str = "hugrgate",
                  project_license: str = "Apache-2.0") -> LicenseReport:
    """Audit the runtime dependency closure plus the project itself."""
    closure = runtime_closure(pyproject)
    full = audit_installed()
    report = LicenseReport(
        packages=[p for p in full.packages
                  if p.name.lower() in closure])
    report.packages.append(PackageLicense(
        name=project_name, version="1.0.0",
        declaration=project_license,
        status=classify_license(project_license)))
    return report
