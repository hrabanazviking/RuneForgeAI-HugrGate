"""Slice 369 — Fairness hooks.

Covers: parity gap math, worst_group, flagged() queries,
disparate-impact ratios and the four-fifths check, validation
(missing group key, tiny groups, single group, empty items, bad
min_group_size), non-categorical specs having no selection data,
and serialization round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    FairnessReport,
    fairness_evaluate,
)


def _dataset():
    # Group A: stub ("a") always right.  Group B: half right.
    items = []
    for i in range(20):
        items.append({"state": {"x": i}, "expected": "a", "group": "A"})
    for i in range(20):
        expected = "a" if i % 2 == 0 else "b"
        items.append({"state": {"x": i}, "expected": expected,
                      "group": "B"})
    return {
        "name": "fairness-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": items,
    }


def test_gap_and_worst_group(gate_with_stub):
    report = fairness_evaluate(_dataset(), gate_with_stub, ["stub"],
                               group_key="group")
    assert report.groups == ["A", "B"]
    assert report.group_sizes == {"A": 20, "B": 20}
    assert report.gap("stub", "accuracy") == pytest.approx(0.5)
    assert report.worst_group("stub", "accuracy") == ("B", 0.5)


def test_flagged(gate_with_stub):
    report = fairness_evaluate(_dataset(), gate_with_stub, ["stub"],
                               group_key="group")
    assert report.flagged("accuracy", max_gap=0.1) == [("stub", 0.5)]
    assert report.flagged("accuracy", max_gap=0.9) == []
    with pytest.raises(EvalError):
        report.flagged("accuracy", max_gap=-0.1)


def test_disparate_impact(gate_with_stub):
    report = fairness_evaluate(_dataset(), gate_with_stub, ["stub"],
                               group_key="group")
    rates = report.selection_rates["stub"]
    # Stub always picks "a": selection rate 1.0 in both groups.
    assert rates["a"] == {"A": 1.0, "B": 1.0}
    assert rates["b"] == {"A": 0.0, "B": 0.0}
    assert report.disparate_impact_ratio("stub", "a") == pytest.approx(
        1.0)
    assert report.disparate_impact_ratio("stub", "b") is None
    assert report.passes_four_fifths("stub") == {"a": True, "b": False}


def test_disparate_impact_uniform_backend(gate_with_stub):
    from tests.conftest import StubBackend
    # A backend that always picks "b": uniform selection, zero impact.
    gate_with_stub.register(StubBackend(name="b-stub", value="b"))
    report = fairness_evaluate(_dataset(), gate_with_stub, ["b-stub"],
                               group_key="group")
    assert report.disparate_impact_ratio("b-stub", "b") == \
        pytest.approx(1.0)
    assert report.gap("b-stub", "accuracy") == pytest.approx(0.5)


def test_missing_group_key_refused(gate_with_stub):
    ds = _dataset()
    del ds["items"][0]["group"]
    with pytest.raises(EvalError):
        fairness_evaluate(ds, gate_with_stub, ["stub"],
                          group_key="group")


def test_tiny_groups_rejected(gate_with_stub):
    ds = _dataset()
    ds["items"] = [i for i in ds["items"] if i["group"] == "A"][:15] + [
        i for i in ds["items"] if i["group"] == "B"][:3]
    with pytest.raises(EvalError) as ei:
        fairness_evaluate(ds, gate_with_stub, ["stub"],
                          group_key="group")
    assert "min_group_size" in str(ei.value)
    # Explicit opt-in works.
    report = fairness_evaluate(ds, gate_with_stub, ["stub"],
                               group_key="group", min_group_size=3)
    assert report.groups == ["A", "B"]
    with pytest.raises(EvalError):
        fairness_evaluate(ds, gate_with_stub, ["stub"],
                          group_key="group", min_group_size=0)


def test_single_group_rejected(gate_with_stub):
    ds = _dataset()
    for item in ds["items"]:
        item["group"] = "A"
    with pytest.raises(EvalError):
        fairness_evaluate(ds, gate_with_stub, ["stub"],
                          group_key="group")


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset()
    ds["items"] = []
    with pytest.raises(EvalError):
        fairness_evaluate(ds, gate_with_stub, ["stub"],
                          group_key="group")


def test_binary_spec_no_impact_table(gate_with_stub):
    from hugrgate.backend import Backend
    from hugrgate.result import DecisionResult

    class BinaryStub(Backend):
        name = "bin-stub"

        def capabilities(self):
            return {"spec_types": ["binary"]}

        def supports(self, spec):
            return spec.type == "binary"

        def evaluate(self, state, spec, context=None):
            return DecisionResult(value="true", probability=1.0,
                                  distribution={"true": 1.0,
                                                "false": 0.0})

    gate_with_stub.register(BinaryStub())
    ds = {
        "name": "fairness-binary",
        "version": "1.0.0",
        "spec": DecisionSpec(type="binary",
                             statement="ok?").to_dict(),
        "items": [{"state": {"x": i}, "expected": "true", "group": g}
                  for i in range(12) for g in ("A", "B")],
    }
    report = fairness_evaluate(ds, gate_with_stub, ["bin-stub"],
                               group_key="group")
    assert report.selection_rates == {}
    assert report.passes_four_fifths("bin-stub") is None
    assert report.disparate_impact_ratio("bin-stub", "yes") is None


def test_report_roundtrip(gate_with_stub):
    report = fairness_evaluate(_dataset(), gate_with_stub, ["stub"],
                               group_key="group")
    clone = FairnessReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.gap("stub", "accuracy") == pytest.approx(0.5)
