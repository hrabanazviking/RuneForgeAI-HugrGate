"""Slice 368 — Shift evaluation.

Covers: source/target degradation math, degraded() queries for
higher- and lower-better metrics, label PSI (identical ~ 0, shifted
> 0, categorical and numeric, validation), cohort validation
(missing keys, empty cohorts, overlapping values), and serialization
round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import EvalError
from hugrgate.evlab import ShiftReport, label_psi, shift_evaluate


def _dataset():
    items = []
    for i in range(40):
        period = "2024" if i < 20 else "2025"
        # In 2024 the stub ("a") is right; in 2025 labels drift to "b".
        expected = "a" if period == "2024" else "b"
        items.append({"state": {"x": i}, "expected": expected,
                      "period": period})
    return {
        "name": "shift-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": items,
    }


def test_degradation_math(gate_with_stub):
    report = shift_evaluate(_dataset(), gate_with_stub, ["stub"],
                            shift_key="period",
                            source="2024", target="2025")
    assert report.n_source == 20
    assert report.n_target == 20
    info = report.backends["stub"]
    assert info["source"]["accuracy"] == pytest.approx(1.0)
    assert info["target"]["accuracy"] == pytest.approx(0.0)
    assert report.degradation("stub", "accuracy") == pytest.approx(-1.0)


def test_degraded_query(gate_with_stub):
    report = shift_evaluate(_dataset(), gate_with_stub, ["stub"],
                            shift_key="period",
                            source="2024", target="2025")
    assert report.degraded("accuracy", min_drop=0.05) == [("stub", 1.0)]
    assert report.degraded("accuracy", min_drop=1.5) == []
    # Lower-better: brier rises under shift.
    flagged = report.degraded("brier_score", min_drop=0.05,
                              higher_better=False)
    assert [b for b, _ in flagged] == ["stub"]
    with pytest.raises(EvalError):
        report.degraded("accuracy", min_drop=-1.0)
    with pytest.raises(EvalError):
        report.degradation("ghost", "accuracy")


def test_label_psi_tracks_shift():
    # PSI on the labels directly: identical vs shifted.
    assert label_psi(["a"] * 20, ["a"] * 20) == pytest.approx(0.0)
    assert label_psi(["a"] * 20, ["b"] * 20) > 1.0
    assert label_psi([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == \
        pytest.approx(0.0)
    assert label_psi([1.0] * 50, [9.0] * 50) > 0.5


def test_label_psi_validation():
    with pytest.raises(EvalError):
        label_psi([], ["a"])
    with pytest.raises(EvalError):
        label_psi(["a"], ["a"], bins=1)
    with pytest.raises(EvalError):
        label_psi([object()], [object()])


def test_report_carries_psi(gate_with_stub):
    report = shift_evaluate(_dataset(), gate_with_stub, ["stub"],
                            shift_key="period",
                            source="2024", target="2025")
    # Labels fully flip between cohorts: large PSI.
    assert report.label_psi > 1.0
    assert report.shift_key == "period"


def test_multi_value_cohorts(gate_with_stub):
    ds = _dataset()
    for item in ds["items"][:10]:
        item["period"] = "2023"
    report = shift_evaluate(ds, gate_with_stub, ["stub"],
                            shift_key="period",
                            source=["2023", "2024"], target="2025")
    assert report.n_source == 20
    assert report.n_target == 20


def test_missing_key_refused(gate_with_stub):
    ds = _dataset()
    del ds["items"][0]["period"]
    with pytest.raises(EvalError):
        shift_evaluate(ds, gate_with_stub, ["stub"], shift_key="period",
                       source="2024", target="2025")


def test_empty_cohort_rejected(gate_with_stub):
    with pytest.raises(EvalError):
        shift_evaluate(_dataset(), gate_with_stub, ["stub"],
                       shift_key="period",
                       source="2024", target="1999")


def test_overlapping_values_rejected(gate_with_stub):
    with pytest.raises(EvalError):
        shift_evaluate(_dataset(), gate_with_stub, ["stub"],
                       shift_key="period",
                       source=["2024", "2025"], target="2025")


def test_empty_items_rejected(gate_with_stub):
    ds = _dataset()
    ds["items"] = []
    with pytest.raises(EvalError):
        shift_evaluate(ds, gate_with_stub, ["stub"], shift_key="period",
                       source="2024", target="2025")


def test_report_roundtrip(gate_with_stub):
    report = shift_evaluate(_dataset(), gate_with_stub, ["stub"],
                            shift_key="period",
                            source="2024", target="2025")
    clone = ShiftReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.degradation("stub", "accuracy") == pytest.approx(-1.0)
