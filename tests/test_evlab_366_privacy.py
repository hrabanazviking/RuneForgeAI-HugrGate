"""Slice 366 — Privacy-aware evaluation.

Covers: PII scan findings (email/phone), clean datasets, kind
filtering, max_items validation, assert_privacy refusal and its
message, randomized_response_q math and validation, utility-curve
shape (baseline, degradation at low epsilon, determinism),
epsilon_for_accuracy, disclaimer presence, and serialization
round-trips.
"""

from __future__ import annotations

import math

import pytest

from hugrgate import DecisionSpec
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    PIIReport,
    PrivacyUtilityCurve,
    privacy_utility_curve,
    randomized_response_q,
    scan_dataset_pii,
)


def _dataset(states):
    return {
        "name": "pii-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": s, "expected": "a"} for s in states],
    }


# --- PII scanning --------------------------------------------------------------------

def test_scan_finds_email_and_phone():
    ds = _dataset([
        {"note": "contact alice@example.com urgently"},
        {"note": "call 415-555-0132 today"},
        {"note": "nothing to see here"},
    ])
    report = scan_dataset_pii(ds)
    assert report.total_findings >= 2
    assert report.findings_by_kind.get("email", 0) >= 1
    assert report.findings_by_kind.get("phone", 0) >= 1
    assert report.items_scanned == 3
    assert report.items_with_pii == 2
    assert report.requires_restricted is True


def test_clean_dataset():
    ds = _dataset([{"note": "nothing to see here"}])
    report = scan_dataset_pii(ds)
    assert report.total_findings == 0
    assert report.requires_restricted is False
    report.assert_privacy()  # must not raise


def test_assert_privacy_refuses_with_guidance():
    ds = _dataset([{"note": "mail bob@example.com"}])
    report = scan_dataset_pii(ds)
    with pytest.raises(EvalError) as ei:
        report.assert_privacy()
    assert "restricted" in str(ei.value)
    assert ei.value.details["pii_kinds"] == ["email"]


def test_kind_filtering():
    ds = _dataset([{"note": "mail bob@example.com, call 415-555-0132"}])
    report = scan_dataset_pii(ds, kinds=["email"])
    assert set(report.findings_by_kind) == {"email"}


def test_max_items_validation():
    ds = _dataset([{"note": "x"}])
    with pytest.raises(EvalError):
        scan_dataset_pii(ds, max_items=0)
    report = scan_dataset_pii(ds, max_items=1)
    assert report.items_scanned == 1


def test_report_roundtrip():
    ds = _dataset([{"note": "mail bob@example.com"}])
    report = scan_dataset_pii(ds)
    clone = PIIReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.requires_restricted is True


# --- randomized response math ------------------------------------------------------------------

def test_flip_probability():
    assert randomized_response_q(float("inf")) == pytest.approx(0.0)
    assert randomized_response_q(0.0) == pytest.approx(0.5)
    assert randomized_response_q(10.0) < 1e-4
    assert randomized_response_q(1.0) == pytest.approx(
        1.0 / (1.0 + math.e))
    with pytest.raises(EvalError):
        randomized_response_q(-1.0)
    with pytest.raises(EvalError):
        randomized_response_q(float("nan"))


# --- utility curves ----------------------------------------------------------------------------------

def _eval_dataset(n=80):
    return {
        "name": "util-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i}, "expected": "a"} for i in range(n)],
    }


def test_utility_curve_shape(gate_with_stub):
    curve = privacy_utility_curve(
        _eval_dataset(), gate_with_stub, "stub",
        [0.5, 1.0, 2.0, 5.0, float("inf")], seed=7)
    assert curve.backend == "stub"
    assert curve.baseline_accuracy == pytest.approx(1.0)
    assert curve.disclaimer.startswith("Simulation")
    by_eps = {pt.epsilon: pt for pt in curve.points}
    # No noise at infinity: baseline recovered exactly.
    assert by_eps[float("inf")].accuracy == pytest.approx(1.0)
    assert by_eps[float("inf")].flip_q == pytest.approx(0.0)
    # Heavy noise degrades accuracy toward chance (0.5 for binary).
    assert by_eps[0.5].accuracy < 0.9
    assert by_eps[0.5].flip_q == pytest.approx(
        randomized_response_q(0.5))


def test_utility_curve_deterministic(gate_with_stub):
    kw = dict(epsilons=[1.0, 3.0], seed=11)
    c1 = privacy_utility_curve(_eval_dataset(), gate_with_stub,
                               "stub", **kw)
    c2 = privacy_utility_curve(_eval_dataset(), gate_with_stub,
                               "stub", **kw)
    assert c1.to_dict() == c2.to_dict()


def test_epsilon_for_accuracy(gate_with_stub):
    curve = privacy_utility_curve(
        _eval_dataset(), gate_with_stub, "stub",
        [0.5, 1.0, 2.0, 5.0, float("inf")], seed=7)
    eps = curve.epsilon_for_accuracy(0.95)
    assert eps is not None and eps < float("inf")
    with pytest.raises(EvalError):
        curve.epsilon_for_accuracy(2.0)
    # Unreachable target -> None (synthetic low-accuracy curve).
    from hugrgate.evlab import PrivacyUtilityPoint
    low = PrivacyUtilityCurve(
        backend="x", baseline_accuracy=0.6,
        points=[PrivacyUtilityPoint(epsilon=1.0, flip_q=0.27,
                                    accuracy=0.6, n=10)])
    assert low.epsilon_for_accuracy(0.9) is None
    assert low.epsilon_for_accuracy(0.5) == pytest.approx(1.0)


def test_curve_validation(gate_with_stub):
    with pytest.raises(EvalError):
        privacy_utility_curve(_eval_dataset(), gate_with_stub,
                              "stub", [])
    with pytest.raises(EvalError):
        privacy_utility_curve(_eval_dataset(), gate_with_stub,
                              "stub", [-1.0])
    ds = _eval_dataset(5)
    ds["items"] = []
    with pytest.raises(EvalError):
        privacy_utility_curve(ds, gate_with_stub, "stub", [1.0])


def test_curve_roundtrip(gate_with_stub):
    curve = privacy_utility_curve(_eval_dataset(), gate_with_stub,
                                  "stub", [1.0, float("inf")], seed=3)
    clone = PrivacyUtilityCurve.from_dict(curve.to_dict())
    assert clone.to_dict() == curve.to_dict()
    assert clone.disclaimer == curve.disclaimer
