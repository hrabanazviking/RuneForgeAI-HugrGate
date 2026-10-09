"""Slice 005 — dead-code elimination.

Guards the cleanup: no unused imports anywhere under ``hugrgate/``,
the previously-unreferenced public names are now exercised
(``register_model`` round-trips through the catalogue; ``BenchmarkConfig``
is a first-class ``run_benchmark`` input), and ``run_benchmark`` keeps
its old keyword calling convention.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hugrgate import DecisionPolicy
from hugrgate.bench import BenchmarkConfig, run_benchmark
from hugrgate.server import ModelInfo, list_models, register_model

ROOT = Path(__file__).resolve().parent.parent


def _imported_names(tree: ast.Module) -> dict[str, int]:
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name != "__future__":
                    found[a.asname or a.name.split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for a in node.names:
                if a.name != "*":
                    found[a.asname or a.name] = node.lineno
    return found


def test_no_unused_imports_in_package():
    offenders = []
    for path in sorted((ROOT / "hugrgate").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for name, lineno in _imported_names(tree).items():
            # whole-word occurrences; the import line itself counts as one
            uses = sum(
                1 for _ in
                __import__("re").finditer(rf"\b{name}\b", src)
            )
            if uses < 2:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno} {name}")
    assert not offenders, f"unused imports: {offenders}"


def test_register_model_round_trips_through_catalogue():
    before = len(list_models())
    register_model(ModelInfo(name="dead-code-probe-1.0", backend="rules",
                             spec_types=["categorical"]))
    try:
        names = [m.name for m in list_models()]
        assert "dead-code-probe-1.0" in names
        assert len(list_models()) == before + 1
    finally:
        # leave no trace: restore the catalogue
        from hugrgate import server as _server

        _server._MODEL_CATALOG[:] = [
            m for m in _server._MODEL_CATALOG if m.name != "dead-code-probe-1.0"
        ]
    assert len(list_models()) == before


def test_benchmark_config_drives_run_benchmark():
    from hugrgate import HugrGate
    from hugrgate.backends.rules import Rule, RuleBackend

    dataset = {
        "name": "probe",
        "spec": {"type": "categorical", "options": ["yes", "no"]},
        "items": [
            {"state": {"x": 2.0}, "expected": "yes"},
            {"state": {"x": 0.0}, "expected": "no"},
        ],
    }
    gate = HugrGate()
    gate.register(RuleBackend(
        [Rule(condition={"field": "x", "gt": 1.0}, then="yes", confidence=0.9),
         Rule(condition=None, then="no", confidence=0.9)], name="r"))

    via_kwargs = run_benchmark(dataset, gate, backends=["r"], max_items=1)
    via_config = run_benchmark(
        dataset, gate,
        config=BenchmarkConfig(backends=["r"], max_items=1),
    )
    assert via_kwargs["n_items"] == 1
    assert via_config["n_items"] == 1
    assert (via_config["backends"]["r"]["accuracy"]
            == via_kwargs["backends"]["r"]["accuracy"])

    # explicit keywords win over the config
    mixed = run_benchmark(dataset, gate, max_items=2,
                          config=BenchmarkConfig(max_items=1))
    assert mixed["n_items"] == 2


def test_benchmark_config_defaults_are_all_none():
    cfg = BenchmarkConfig()
    assert cfg.backends is None and cfg.policy is None and cfg.max_items is None
    assert isinstance(cfg.policy or DecisionPolicy(), DecisionPolicy)


# --- failure / boundary --------------------------------------------------------

def test_run_benchmark_rejects_empty_backend_selection():
    from hugrgate import HugrGate

    dataset = {
        "name": "probe",
        "spec": {"type": "categorical", "options": ["yes", "no"]},
        "items": [{"state": {"x": 1.0}, "expected": "yes"}],
    }
    with pytest.raises(ValueError, match="no backends available"):
        run_benchmark(dataset, HugrGate(), backends=[])
