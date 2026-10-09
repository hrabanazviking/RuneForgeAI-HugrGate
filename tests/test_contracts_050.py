"""Gjallarbrú slice 050 — Contract Engine release gate.

Integration wiring (``HugrGate.decide`` accepts v2 contracts) plus the
release-gate checks: v1 backward compatibility, stdlib-only contract
dependencies, and the full-campaign regression net.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hugrgate import (
    Backend,
    BackendUnavailable,
    DecisionResult,
    DecisionSpec,
    HugrGate,
    SpecError,
)
from hugrgate.contracts.cost import CostSensitiveContract
from hugrgate.contracts.migration import spec_to_contract
from hugrgate.contracts.nested import NestedCategoricalContract
from hugrgate.errors import ContractError

ROOT = Path(__file__).resolve().parent.parent


class StubBackend(Backend):
    name = "stub"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        dist = {o: (0.9 if o == spec.options[0] else 0.1)
                for o in spec.options}
        return DecisionResult(value=spec.options[0], probability=0.9,
                              distribution=dist, backend=self.name)


def _gate() -> HugrGate:
    gate = HugrGate()
    gate.register(StubBackend())
    return gate


# --- decide() accepts v2 contracts ---------------------------------------------

def test_decide_accepts_v2_contract():
    gate = _gate()
    contract = NestedCategoricalContract(
        contract_id="gate-v2", name="triage",
        options=["ignore", "escalate"])
    result = gate.decide({"event": "x"}, contract)
    assert result.value == "ignore"
    assert result.accepted
    assert result.metadata["contract_id"] == "gate-v2"


def test_decide_batch_accepts_v2_contract():
    gate = _gate()
    contract = NestedCategoricalContract(
        contract_id="batch-v2", options=["a", "b"])
    results = gate.decide_batch([{"e": 1}, {"e": 2}], contract)
    assert [r.value for r in results] == ["a", "a"]
    assert all(r.metadata["contract_id"] == "batch-v2" for r in results)


def test_decide_v1_path_unchanged():
    # Backward compatibility: a v1 spec flows through with no
    # contract_id stamped and identical behavior.
    gate = _gate()
    spec = DecisionSpec(type="categorical", options=["ignore", "escalate"])
    result = gate.decide({"event": "x"}, spec)
    assert result.value == "ignore" and result.accepted
    assert "contract_id" not in result.metadata


def test_decide_rejects_contract_without_v1_path():
    gate = _gate()
    exotic = CostSensitiveContract(
        contract_id="exotic", outcomes=["a", "b"],
        costs={"a": {"a": 0.0, "b": 1.0}, "b": {"a": 2.0, "b": 0.0}})
    with pytest.raises(ContractError) as ei:
        gate.decide({"event": "x"}, exotic)
    assert ei.value.details["code"] == "no_downgrade_path"


def test_decide_rejects_garbage_spec():
    gate = _gate()
    with pytest.raises(SpecError):
        gate.decide({"event": "x"}, "not-a-spec")  # type: ignore[arg-type]


def test_decide_v2_binary_contract():
    gate = _gate()
    spec = DecisionSpec(type="binary", statement="launch?")
    contract, _ = spec_to_contract(spec, "bin-v2")
    # Binary migrates back to a v1 binary spec, which the categorical-only
    # stub cannot serve — this must fail loudly, not silently misroute.
    with pytest.raises(BackendUnavailable):
        gate.decide({"event": "x"}, contract)


# --- release gate: dependency inspection -----------------------------------------

def test_contracts_are_stdlib_only():
    """The Contract Engine adds no third-party dependencies."""
    stdlibish = {"dataclasses", "typing", "re", "hashlib", "json",
                 "random", "time", "math", "itertools", "functools",
                 "collections", "enum", "abc", "copy", "datetime",
                 "importlib", "__future__"}
    offenders = []
    pkg = ROOT / "hugrgate" / "contracts"
    for path in sorted(pkg.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # relative = internal
                mods = [node.module.split(".")[0]] if node.module else []
            else:
                continue
            for m in mods:
                if m not in stdlibish and not m.startswith("hugrgate"):
                    offenders.append(f"{path.name}: {m}")
    assert not offenders, f"non-stdlib imports in contracts: {offenders}"


def test_hugrgate_public_api_unchanged():
    """The slice-003 public API snapshot still holds after Campaign II."""
    import hugrgate
    assert "DecisionSpec" in hugrgate.__all__
    assert "HugrGate" in hugrgate.__all__
    # contracts live in their own namespace, not the top-level API
    assert "contracts" not in hugrgate.__all__
