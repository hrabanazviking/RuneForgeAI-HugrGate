"""Slice 004 — dependency graph audit.

Internal layering rules (eager imports only) and third-party dependency
coverage: every third-party import must be provided by the base install
or by a declared extra, and the layering invariants below must hold.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

pytestmark = pytest.mark.gate
ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "tools" / "gen_arch_map.py"


def _load_gen():
    spec = importlib.util.spec_from_file_location("gen_arch_map", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _eager_edges() -> dict[str, set[str]]:
    """module -> eagerly imported internal modules (resolved)."""
    gen = _load_gen()
    modules = gen._scan_modules()
    names = set(modules)
    edges: dict[str, set[str]] = {}
    for mod, info in modules.items():
        resolved = set()
        for target, lazy in info["edges"].items():
            r = gen.resolve(target, names)
            if r and r != mod and not lazy:
                resolved.add(r)
        edges[mod] = resolved
    return edges


def _is_backend(mod: str) -> bool:
    return mod.startswith("hugrgate.backends.")


def _is_calibration(mod: str) -> bool:
    return mod == "hugrgate.calibration" or mod.startswith("hugrgate.calibration.")


CONTRACTS = {
    "hugrgate.errors", "hugrgate.spec", "hugrgate.result",
    "hugrgate.backend", "hugrgate.policy", "hugrgate.validation",
}
SERVICE = {"hugrgate.server", "hugrgate.daemon", "hugrgate.cli", "hugrgate.client"}
BACKEND_ALLOWED = CONTRACTS | {"hugrgate.features", "hugrgate.models"}
CALIB_ALLOWED = {
    "hugrgate.errors", "hugrgate.backend",
    "hugrgate.result", "hugrgate.spec",
    # Slice 095: epistemic adapters flag results for human review via
    # hugrgate.abstain.mark_for_review.  abstain is a core domain module
    # (not service layer) — precedent: hugrgate.threshold imports it too.
    "hugrgate.abstain",
}


# --- internal layering ---------------------------------------------------------

def test_contracts_layer_imports_only_contracts():
    violations = [
        f"{m} -> {t}" for m, ts in _eager_edges().items()
        if m in CONTRACTS for t in ts if t not in CONTRACTS
    ]
    assert not violations, f"contracts layer escapes: {violations}"


def test_backends_stay_below_the_service_layer():
    violations = [
        f"{m} -> {t}" for m, ts in _eager_edges().items()
        if _is_backend(m)
        for t in ts
        if not (t in BACKEND_ALLOWED or _is_backend(t))
    ]
    assert not violations, f"backend layering violations: {violations}"


def test_calibration_stays_below_the_service_layer():
    violations = [
        f"{m} -> {t}" for m, ts in _eager_edges().items()
        if _is_calibration(m)
        for t in ts
        if not (t in CALIB_ALLOWED or _is_calibration(t))
    ]
    assert not violations, f"calibration layering violations: {violations}"


def test_only_service_modules_import_service_modules():
    violations = [
        f"{m} -> {t}" for m, ts in _eager_edges().items()
        if m not in SERVICE for t in ts if t in SERVICE
    ]
    assert not violations, f"service layer leaks: {violations}"


# --- third-party coverage ------------------------------------------------------

THIRD_PARTY_PROVIDERS: dict[str, set[str]] = {
    # top-level import name -> extras (or {"base"}) that provide it
    "yaml": {"base"},
    "numpy": {"ml", "bench"},
    "sklearn": {"ml"},
    "scipy": {"ml"},
    "llama_cpp": {"llm"},
    "transformers": {"nli"},
    "torch": {"nli"},
    "fastapi": {"server"},
    "uvicorn": {"server"},
    "httpx": {"server"},
    "pytest": {"test"},
    "mypy": {"typecheck"},
    "ruff": {"lint"},
    "coverage": {"lint"},
    "onnxruntime": {"onnx"},
}
# Declared extras with no current importer (documented reservations).
RESERVED_EXTRAS = {"onnx": "reserved for a future ONNX backend (slice 004 audit)"}

_STDLIB = {
    "__future__", "abc", "argparse", "ast", "asyncio", "collections",
    "contextlib", "copy", "dataclasses", "datetime", "enum", "hashlib",
    "importlib", "inspect", "io", "itertools", "json", "logging", "math",
    "os", "pathlib", "pickle", "platform", "random", "re", "shutil",
    "signal", "socket", "statistics", "string", "subprocess", "sys",
    "tempfile", "threading", "time", "tomllib", "traceback", "typing",
    "unittest", "uuid", "warnings", "functools", "operator", "textwrap",
    "csv", "gzip", "zipfile", "email", "html", "http", "urllib",
    "concurrent",
}
# First-party modules imported via sys.path tricks in tests/benchmarks.
_LOCAL_MODULES = {"event_triage", "build", "ensemble_fakes"}


def _third_party_imports() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for top in ("hugrgate", "tests", "benchmarks"):
        for path in sorted((ROOT / top).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            mod = ".".join(path.relative_to(ROOT).with_suffix("").parts)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split(".")[0]]
                for n in names:
                    if n in _LOCAL_MODULES:
                        continue
                    if n not in _STDLIB and not n.startswith("hugrgate"):
                        found.setdefault(n, set()).add(mod)
    return found


def _pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def test_every_third_party_import_is_declared():
    project = _pyproject()
    base = set(project["project"]["dependencies"])
    extras = project["project"]["optional-dependencies"]
    provided: dict[str, set[str]] = {}
    for dep in base:
        provided.setdefault(dep.split(">")[0].split("=")[0].split()[0], set()).add("base")
    for extra, deps in extras.items():
        for dep in deps:
            name = re.split(r"[><= ;\[]", dep)[0].strip()
            provided.setdefault(name, set()).add(extra)
    # normalize distribution names to import names
    normalized = {}
    for dist, exs in provided.items():
        normalized.setdefault(
            {
                "pyyaml": "yaml",
                "scikit-learn": "sklearn",
                "llama-cpp-python": "llama_cpp",
            }.get(dist, dist),
            set(),
        ).update(exs)

    undeclared = []
    for top, mods in _third_party_imports().items():
        want = THIRD_PARTY_PROVIDERS.get(top)
        if want is None:
            undeclared.append(f"{top} (imported by {sorted(mods)}): unknown provider")
            continue
        have = normalized.get(top, set())
        if not (want & have):
            undeclared.append(f"{top}: imported but no declared extra provides it")
    assert not undeclared, f"undeclared third-party imports: {undeclared}"


def test_base_dependencies_stay_minimal():
    project = _pyproject()
    base = [re.split(r"[><= ;\[]", d)[0].strip() for d in project["project"]["dependencies"]]
    assert base == ["pyyaml"], f"base install must stay minimal, got: {base}"


def test_no_extra_is_silently_unused():
    project = _pyproject()
    extras = set(project["project"]["optional-dependencies"])
    used = set()
    for top, providers in THIRD_PARTY_PROVIDERS.items():
        if top in _third_party_imports():
            used.update(providers)
    unused = extras - used - set(RESERVED_EXTRAS)
    assert not unused, f"extras with no importer and no reservation: {unused}"


# --- optional-dependency behavior -----------------------------------------------

_BLOCKER_PREAMBLE = """
import sys, importlib.abc
class _Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {"numpy", "sklearn", "scipy"}:
            raise ImportError("blocked for test: " + name)
sys.meta_path.insert(0, _Blocker())
"""


def _run_blocked(probe: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _BLOCKER_PREAMBLE + probe],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_missing_numpy_raises_deliberate_calibration_error():
    proc = _run_blocked(
        "from hugrgate.calibration.metrics import brier_score\n"
        "brier_score([0, 1], [0.2, 0.8])\n"
    )
    assert proc.returncode != 0
    assert "CalibrationError" in proc.stderr
    assert "hugrgate[ml]" in proc.stderr


def test_missing_sklearn_raises_deliberate_backend_error():
    proc = _run_blocked(
        "from hugrgate.backends.logreg import _require_ml\n"
        "_require_ml()\n"
    )
    assert proc.returncode != 0
    assert "BackendError" in proc.stderr
    assert "hugrgate[ml]" in proc.stderr


def test_stdlib_only_path_works_without_numpy():
    proc = _run_blocked(
        "from hugrgate.backends.rules import RuleBackend, Rule\n"
        "from hugrgate import HugrGate, DecisionSpec, DecisionPolicy\n"
        "b = RuleBackend([Rule(condition={'field': 'x', 'gt': 1.5}, then='yes',"
        " confidence=0.9)], name='r')\n"
        "g = HugrGate(); g.register(b)\n"
        "r = g.decide({'x': 2.0},\n"
        "  DecisionSpec(type='categorical', options=['yes', 'no']),\n"
        "  DecisionPolicy())\n"
        "assert r.value == 'yes' and r.probability == 0.9, r\n"
        "print('RULES-OK')\n"
    )
    assert proc.returncode == 0, proc.stderr
    assert "RULES-OK" in proc.stdout


# --- failure / boundary ----------------------------------------------------------

def test_layer_predicates_reject_unknown_modules():
    assert not _is_backend("hugrgate.core")
    assert not _is_calibration("hugrgate.core")
    assert _is_backend("hugrgate.backends.rules")
    assert _is_calibration("hugrgate.calibration")
    assert _is_calibration("hugrgate.calibration.platt")
