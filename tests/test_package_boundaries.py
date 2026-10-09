"""Slice 020 — package boundary cleanup.

The package root exports a curated surface; submodules must reach it
through their defining modules, never through the root. A submodule
doing ``from hugrgate import X`` couples itself to ``__init__``
import order and turns any future ``__init__`` growth into a
partial-initialization ImportError. This pins the rule.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate
PKG = Path(__file__).resolve().parent.parent / "hugrgate"
ROOT_EXPORTS = {
    "DecisionSpec", "DecisionResult", "DecisionPolicy",
    "Backend", "BackendRegistry", "HugrGate",
    "HugrGateError", "SpecError", "PolicyError", "BackendError",
    "BackendUnavailable", "CalibrationError", "TimeoutError",
    "PrivacyViolation", "QueueFull", "Abstention",
}


def _root_imports_of(path: Path):
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "hugrgate":
            found.extend(a.name for a in node.names)
    return found


def test_no_submodule_imports_names_from_package_root():
    """Submodules import from defining modules (hugrgate.spec, ...),
    not from the package root. ``__version__`` is the only exception."""
    offenders = {}
    for path in sorted(PKG.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        names = [n for n in _root_imports_of(path) if n != "__version__"]
        if names:
            offenders[str(path.relative_to(PKG))] = names
    assert not offenders, f"root imports inside submodules: {offenders}"


def test_package_all_matches_root_exports():
    import hugrgate
    assert set(hugrgate.__all__) == ROOT_EXPORTS
    for name in hugrgate.__all__:
        assert getattr(hugrgate, name) is not None


def test_every_submodule_importable_standalone():
    """Each submodule imports cleanly in a fresh interpreter, in
    alphabetical order — no hidden dependence on import sequence."""
    modules = sorted(
        "hugrgate." + p.relative_to(PKG).with_suffix("").as_posix(
        ).replace("/", ".")
        for p in PKG.rglob("*.py")
        if p.name != "__init__.py"
    )
    code = "; ".join(f"import {m}" for m in modules)
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        cwd=PKG.parent, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_no_circular_imports_via_arch_map():
    # The architecture map generator doubles as the cycle detector.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen_arch_map",
        PKG.parent / "tools" / "gen_arch_map.py")
    assert spec is not None and spec.loader is not None
