"""Python-version matrix validation for the 1.0 release (slice 478).

HugrGate declares ``requires-python = ">=3.10"``. This module turns
that declaration into a checked matrix instead of a hope:

- :data:`SUPPORTED_MINORS` — the minor versions the 1.0 release
  claims: 3.10 through 3.13.
- :func:`read_requires_python` — parse the lower bound out of
  ``pyproject.toml``.
- :func:`check_syntax_compat` — prove every ``hugrgate`` source file
  parses under the *oldest* supported grammar via
  ``ast.parse(feature_version=...)``. New syntax (``match`` is fine
  on 3.10; ``except*``, ``type`` aliases are not) is caught here,
  not on a user's 3.10 box.
- :func:`validate_matrix` — the whole claim in one call: declared
  lower bound, matrix coverage, and syntax compatibility.

The runnable form is ``tools/matrix/python_matrix.py``.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import tomllib

__all__ = [
    "REPO_ROOT",
    "SUPPORTED_MINORS",
    "MatrixReport",
    "check_syntax_compat",
    "read_requires_python",
    "validate_matrix",
]

#: Repository root, derived from this file's location.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Minor versions the 1.0 release supports. 3.10 is the floor from
#: ``requires-python``; 3.13 is the newest stable validated locally.
SUPPORTED_MINORS: tuple[tuple[int, int], ...] = (
    (3, 10),
    (3, 11),
    (3, 12),
    (3, 13),
)


@dataclass(frozen=True)
class MatrixReport:
    """Outcome of :func:`validate_matrix`."""

    requires_python: str
    min_minor: tuple[int, int]
    matrix: tuple[tuple[int, int], ...]
    files_checked: int
    syntax_failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.syntax_failures and self.min_minor in self.matrix


def read_requires_python(pyproject: str | Path) -> str:
    """Extract the ``requires-python`` specifier from ``pyproject.toml``."""
    raw = tomllib.loads(Path(pyproject).read_text(encoding="utf-8"))
    spec = raw.get("project", {}).get("requires-python")
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError(f"{pyproject}: missing project.requires-python")
    return spec.strip()


def _lower_bound(spec: str) -> tuple[int, int]:
    """Pull the ``>=X.Y`` lower bound out of a specifier string."""
    match = re.search(r">=\s*(\d+)\.(\d+)", spec)
    if not match:
        raise ValueError(f"cannot find a >=X.Y lower bound in {spec!r}")
    return (int(match.group(1)), int(match.group(2)))


def check_syntax_compat(
    root: str | Path, min_minor: tuple[int, int]
) -> tuple[int, tuple[str, ...]]:
    """Parse every ``.py`` under ``root`` with the oldest grammar.

    Returns ``(files_checked, failures)`` where each failure is
    ``"<path>:<line>: <message>"``. ``feature_version`` only accepts
    ``(major, minor)`` tuples, which is exactly what we pass.
    """
    root = Path(root)
    failures: list[str] = []
    checked = 0
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        checked += 1
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                feature_version=min_minor,
            )
        except SyntaxError as exc:
            failures.append(f"{path}:{exc.lineno}: {exc.msg}")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(f"{path}: unreadable: {exc}")
    return checked, tuple(failures)


def validate_matrix(
    repo_root: str | Path = REPO_ROOT,
) -> MatrixReport:
    """Validate the full Python-version claim for the repo at ``repo_root``."""
    repo_root = Path(repo_root)
    spec = read_requires_python(repo_root / "pyproject.toml")
    min_minor = _lower_bound(spec)
    checked, failures = check_syntax_compat(repo_root / "hugrgate", min_minor)
    return MatrixReport(
        requires_python=spec,
        min_minor=min_minor,
        matrix=SUPPORTED_MINORS,
        files_checked=checked,
        syntax_failures=failures,
    )
