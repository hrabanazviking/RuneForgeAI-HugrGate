"""Dependency matrices for the 1.0 release (slices 483-484).

Slice 483 (minimums): ``pyproject.toml`` declares minimum versions
(``pyyaml>=6.0``). This module parses them, renders a
``requirements-min.txt`` pinning every runtime dependency at its
declared floor, and checks the running environment against those
floors. The check is dependency-free (no ``packaging`` import —
``packaging`` is not a runtime dependency of HugrGate): version
comparison is numeric over dot-separated segments, which is exact
for the ``>=X.Y`` floors we declare.

Slice 484 (latest) lives in :func:`latest_audit`.
"""

from __future__ import annotations

import ast
import importlib.metadata
import re
from dataclasses import dataclass
from pathlib import Path

import tomllib

#: Repository root for the default pyproject.toml location.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PYPROJECT = REPO_ROOT / "pyproject.toml"

__all__ = [
    "DEFAULT_PYPROJECT",
    "DEPRECATED_PATTERNS",
    "REPO_ROOT",
    "DepReport",
    "DepRequirement",
    "DepStatus",
    "check_minimums",
    "installed_version",
    "latest_audit",
    "parse_requirement",
    "read_runtime_dependencies",
    "render_min_requirements",
    "scan_deprecated_api",
    "version_key",
    "write_min_requirements",
]


@dataclass(frozen=True)
class DepRequirement:
    """One runtime dependency with its declared minimum version."""

    name: str
    minimum: str | None  # None when the spec pins no floor


@dataclass(frozen=True)
class DepStatus:
    """Minimum-check outcome for one dependency."""

    name: str
    minimum: str | None
    installed: str | None
    ok: bool
    reason: str


@dataclass(frozen=True)
class DepReport:
    """Outcome of :func:`check_minimums`."""

    statuses: tuple[DepStatus, ...]

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.statuses)

    def violations(self) -> tuple[DepStatus, ...]:
        return tuple(s for s in self.statuses if not s.ok)


def parse_requirement(spec: str) -> DepRequirement:
    """Parse ``"name>=X.Y"`` / ``"name"`` into a requirement.

    Only the ``>=`` floor is extracted; upper bounds and extras do
    not affect the minimum matrix. Raises :class:`ValueError` on an
    unparseable spec.
    """
    spec = spec.strip()
    match = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:>=\s*([A-Za-z0-9_.\-+]+))?",
                     spec)
    if not match or not match.group(1):
        raise ValueError(f"unparseable requirement: {spec!r}")
    return DepRequirement(name=match.group(1), minimum=match.group(2))


def read_runtime_dependencies(
    pyproject: str | Path = DEFAULT_PYPROJECT,
) -> tuple[DepRequirement, ...]:
    """Parse ``project.dependencies`` from ``pyproject.toml``."""
    raw = tomllib.loads(Path(pyproject).read_text(encoding="utf-8"))
    deps = raw.get("project", {}).get("dependencies")
    if not isinstance(deps, list):
        raise ValueError(f"{pyproject}: missing project.dependencies")
    return tuple(parse_requirement(str(d)) for d in deps)


def version_key(version: str) -> tuple[int, ...]:
    """Numeric comparison key for a dotted version string.

    Non-numeric segments (``rc1``, ``+local``) terminate the numeric
    prefix — the floors we compare are plain ``X.Y`` releases, so a
    pre-release sorts below its release, which is the conservative
    direction for a minimum check.
    """
    parts: list[int] = []
    for segment in re.split(r"[.\-+_]", version.strip()):
        digits = re.match(r"^\d+", segment)
        if not digits:
            break
        parts.append(int(digits.group(0)))
    if not parts:
        raise ValueError(f"unparseable version: {version!r}")
    return tuple(parts)


def installed_version(name: str) -> str | None:
    """Installed distribution version, or None when not installed."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def check_minimums(
    deps: tuple[DepRequirement, ...] | None = None,
) -> DepReport:
    """Check the running environment against declared minimum floors."""
    if deps is None:
        deps = read_runtime_dependencies()
    statuses: list[DepStatus] = []
    for dep in deps:
        installed = installed_version(dep.name)
        if installed is None:
            statuses.append(DepStatus(dep.name, dep.minimum, None, False,
                                      "not installed"))
        elif dep.minimum is None:
            statuses.append(DepStatus(dep.name, None, installed, True,
                                      "no floor declared"))
        elif version_key(installed) >= version_key(dep.minimum):
            statuses.append(DepStatus(dep.name, dep.minimum, installed, True,
                                      "meets floor"))
        else:
            statuses.append(DepStatus(dep.name, dep.minimum, installed, False,
                                      f"{installed} < floor {dep.minimum}"))
    return DepReport(tuple(statuses))


def render_min_requirements(
    deps: tuple[DepRequirement, ...] | None = None,
) -> str:
    """Render ``requirements-min.txt``: every dep pinned at its floor."""
    if deps is None:
        deps = read_runtime_dependencies()
    lines = [
        "# Generated by hugrgate.gauntlet.deps (slice 483).",
        "# Minimum-supported dependency set for HugrGate 1.0.",
    ]
    for dep in deps:
        lines.append(f"{dep.name}=={dep.minimum}" if dep.minimum
                     else dep.name)
    return "\n".join(lines) + "\n"


def write_min_requirements(path: str | Path) -> Path:
    """Write the minimum-requirements file; returns the path."""
    path = Path(path)
    path.write_text(render_min_requirements(), encoding="utf-8")
    return path


#: (regex, reason) pairs for APIs removed or deprecated in the
#: latest releases of our dependencies. ``yaml.load`` without a
#: Loader is an arbitrary-code-execution hole; the naive-UTC
#: datetime constructor is deprecated since 3.12; the numpy aliases
#: died in numpy 1.24.
DEPRECATED_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\byaml\.load\s*\(", "yaml.load() without Loader (use safe_load)"),
    (r"\bdatetime\s*\.\s*utcnow\s*\(", "datetime.utcnow() deprecated (3.12+)"),
    (r"\bnp\.(float_|unicode_|bool8|object0)\b",
     "numpy deprecated alias (removed in numpy 1.24)"),
    (r"\bcollections\.(Mapping|Sequence|MutableMapping)\b",
     "collections ABCs moved to collections.abc (3.10+)"),
    (r"\btime\.clock\s*\(", "time.clock() removed (3.8+)"),
)


def _string_constant_spans(path: Path) -> list[tuple[int, int, int, int]]:
    """Spans of string constants in ``path`` as (lineno, col, end_lineno,
    end_col) tuples.

    Detection corpora (the secscan patterns, this module's own
    ``DEPRECATED_PATTERNS`` table) must *name* dangerous APIs to
    detect them; only real code uses are findings.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"),
                         filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    spans: list[tuple[int, int, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            spans.append((node.lineno, node.col_offset,
                          node.end_lineno or node.lineno,
                          node.end_col_offset or 0))
    return spans


def _in_string(spans: list[tuple[int, int, int, int]],
               lineno: int, col: int) -> bool:
    for sline, scol, eline, ecol in spans:
        if sline == eline:
            if lineno == sline and scol <= col < ecol:
                return True
        elif (lineno == sline and col >= scol) or (lineno == eline
                                                  and col < ecol) \
                or (sline < lineno < eline):
            return True
    return False


def scan_deprecated_api(
    root: str | Path = REPO_ROOT,
) -> tuple[tuple[str, int, str], ...]:
    """Scan ``root`` for deprecated/removed dependency API usage.

    Returns ``(path, lineno, reason)`` findings. Matches inside
    string constants are ignored — detection corpora name these
    APIs to detect them; only real code uses are findings.
    """
    findings: list[tuple[str, int, str]] = []
    for path in sorted(Path(root).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        string_spans = _string_constant_spans(path)
        for lineno, line in enumerate(lines, start=1):
            for pattern, reason in DEPRECATED_PATTERNS:
                for match in re.finditer(pattern, line):
                    if _in_string(string_spans, lineno, match.start()):
                        continue
                    findings.append((str(path), lineno, reason))
    return tuple(findings)


def latest_audit(
    deps: tuple[DepRequirement, ...] | None = None,
) -> dict[str, dict[str, str | bool | None]]:
    """Slice 484: audit the environment against *latest* dependencies.

    Records each runtime dependency's installed version and whether
    it satisfies the declared floor. A dependency newer than the
    floor is expected and fine — the audit's job is to *record* the
    validated-latest set so the 1.0 release notes name real versions,
    and to flag anything *below* the floor (which the minimum
    matrix should already have caught).
    """
    if deps is None:
        deps = read_runtime_dependencies()
    report: dict[str, dict[str, str | bool | None]] = {}
    for dep in deps:
        installed = installed_version(dep.name)
        meets_floor = (
            installed is not None
            and dep.minimum is not None
            and version_key(installed) >= version_key(dep.minimum)
        )
        report[dep.name] = {
            "minimum": dep.minimum,
            "installed": installed,
            "meets_floor": meets_floor,
        }
    return report
