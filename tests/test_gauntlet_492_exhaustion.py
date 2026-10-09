"""Slice 492 — resource exhaustion gauntlet.

Input limits existed but ``HugrGate.decide_batch`` never enforced
``check_batch`` — unbounded batch amplification. This slice wires
the check into ``decide_batch`` (new optional ``limits``
parameter; breaches raise ``InputTooLarge``) and proves the whole
exhaustion battery is contained end to end.
"""

from __future__ import annotations

from typing import Any

import pytest

from hugrgate import DecisionPolicy, DecisionResult, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.errors import InputTooLarge, SpecError
from hugrgate.gauntlet.exhaustion import run_exhaustion_gauntlet
from hugrgate.security.input_limits import InputLimits


class _Stub(Backend):
    name = "stub"

    def capabilities(self) -> dict[str, Any]:
        return {"spec_types": ["categorical"]}

    def supports(self, spec: DecisionSpec) -> bool:
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None) -> DecisionResult:
        return DecisionResult(value="a", probability=0.9,
                              distribution={"a": 0.9, "b": 0.1})


SPEC = DecisionSpec(type="categorical", options=["a", "b"])


def _gate() -> HugrGate:
    gate = HugrGate()
    gate.register(_Stub())
    return gate


def test_exhaustion_battery_contained():
    gate = _gate()
    try:
        report = run_exhaustion_gauntlet(gate, SPEC, DecisionPolicy())
        assert report.contained, report.scenarios
        by_name = {s["name"]: s for s in report.scenarios}
        assert by_name["oversized state"]["error"] == "SpecError"
        assert by_name["oversized batch (count)"]["error"] == "InputTooLarge"
        assert by_name["oversized batch (bytes)"]["error"] == "InputTooLarge"
        assert by_name["control batch"]["contained"] is True
        assert by_name["gate alive after battery"]["contained"] is True
    finally:
        gate.close()


def test_decide_batch_enforces_count_limit():
    gate = _gate()
    try:
        with pytest.raises(InputTooLarge):
            gate.decide_batch([{"x": 1}] * 2000, SPEC, DecisionPolicy())
    finally:
        gate.close()


def test_decide_batch_accepts_custom_limits():
    gate = _gate()
    try:
        limits = InputLimits(max_batch_size=8)
        results = gate.decide_batch([{"x": 1}] * 8, SPEC, DecisionPolicy(),
                                    limits=limits)
        assert len(results) == 8
        with pytest.raises(InputTooLarge):
            gate.decide_batch([{"x": 1}] * 9, SPEC, DecisionPolicy(),
                               limits=limits)
    finally:
        gate.close()


def test_oversized_state_rejected_by_decide():
    gate = _gate()
    try:
        with pytest.raises(SpecError):
            gate.decide({"blob": "x" * 2_000_000}, SPEC, DecisionPolicy())
    finally:
        gate.close()


def test_over_deep_state_rejected_by_decide():
    gate = _gate()
    try:
        deep: dict[str, Any] = {}
        cursor = deep
        for _ in range(100):
            cursor["n"] = {}
            cursor = cursor["n"]
        with pytest.raises(SpecError):
            gate.decide(deep, SPEC, DecisionPolicy())
    finally:
        gate.close()
