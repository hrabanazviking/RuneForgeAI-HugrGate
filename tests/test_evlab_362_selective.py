"""Slice 362 — Selective-risk evaluation.

Covers: RC curve shape (full coverage at threshold 0, risk bounds),
perfect ranking (excess AURC ~ 0), AURC of a perfect classifier,
coverage_at_risk / risk_at_coverage queries, validation errors,
backend-level selective_evaluate end-to-end with ranking, the policy
threshold anchor point, abstention accounting, and serialization
round-trip.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.errors import EvalError
from hugrgate.evlab import (
    SelectiveReport,
    aurc,
    coverage_at_risk,
    oracle_aurc,
    risk_at_coverage,
    risk_coverage_curve,
    selective_evaluate,
)


def test_curve_shape():
    # 60 correct at high confidence, 40 wrong at low confidence.
    correct = [1] * 60 + [0] * 40
    confs = [0.9] * 60 + [0.2] * 40
    curve = risk_coverage_curve(correct, confs)
    assert curve[-1].coverage == pytest.approx(1.0)
    assert curve[-1].risk == pytest.approx(0.4)
    assert curve[0].coverage < 1.0
    assert all(0.0 <= pt.risk <= 1.0 for pt in curve)
    assert all(0.0 < pt.coverage <= 1.0 for pt in curve)


def test_perfect_ranking_zero_excess():
    correct = [1] * 60 + [0] * 40
    confs = [0.9] * 60 + [0.2] * 40
    curve = risk_coverage_curve(correct, confs)
    assert aurc(curve) - oracle_aurc(correct, confs) == pytest.approx(0.0)


def test_perfect_classifier_zero_aurc():
    correct = [1] * 50
    confs = [0.8] * 50
    curve = risk_coverage_curve(correct, confs)
    assert aurc(curve) == pytest.approx(0.0)
    assert oracle_aurc(correct, confs) == pytest.approx(0.0)


def test_random_confidences_positive_excess():
    import random
    rng = random.Random(4)
    correct = [1 if rng.random() < 0.7 else 0 for _ in range(200)]
    confs = [rng.random() for _ in range(200)]
    curve = risk_coverage_curve(correct, confs)
    assert aurc(curve) - oracle_aurc(correct, confs) > 0.01


def test_coverage_at_risk():
    correct = [1] * 60 + [0] * 40
    confs = [0.9] * 60 + [0.2] * 40
    curve = risk_coverage_curve(correct, confs)
    # Keeping only the 0.9-confidence items: 60% coverage, zero risk.
    assert coverage_at_risk(curve, 0.0) == pytest.approx(0.6)
    assert coverage_at_risk(curve, 0.4) == pytest.approx(1.0)
    with pytest.raises(EvalError):
        coverage_at_risk(curve, 1.5)


def test_risk_at_coverage():
    correct = [1] * 60 + [0] * 40
    confs = [0.9] * 60 + [0.2] * 40
    curve = risk_coverage_curve(correct, confs)
    assert risk_at_coverage(curve, 0.6) == pytest.approx(0.0)
    assert risk_at_coverage(curve, 1.0) == pytest.approx(0.4)
    with pytest.raises(EvalError):
        risk_at_coverage(curve, 0.0)
    with pytest.raises(EvalError):
        risk_at_coverage(curve, 1.5)


def test_curve_validation():
    with pytest.raises(EvalError):
        risk_coverage_curve([], [])
    with pytest.raises(EvalError):
        risk_coverage_curve([1, 0], [0.5])
    with pytest.raises(EvalError):
        risk_coverage_curve([1, 2], [0.5, 0.5])
    with pytest.raises(EvalError):
        risk_coverage_curve([1, 0], [0.5, 1.5])
    with pytest.raises(EvalError):
        risk_coverage_curve([1, 0], [0.5, 0.5], n_points=1)
    with pytest.raises(EvalError):
        aurc([])


# --- backend-level -------------------------------------------------------------------

def _dataset(n=120):
    return {
        "name": "sel-smoke",
        "version": "1.0.0",
        "spec": DecisionSpec(type="categorical",
                             options=["a", "b"]).to_dict(),
        "items": [{"state": {"x": i},
                   "expected": "a" if i % 10 < 7 else "b"}
                  for i in range(n)],
    }


def test_selective_evaluate_end_to_end(gate_with_stub):
    from tests.conftest import StubBackend
    # ranked: high confidence when right, low when wrong.
    gate_with_stub.register(StubBackend(name="ranked", value="a",
                                        probability=0.9))
    report = selective_evaluate(_dataset(), gate_with_stub,
                                ["stub", "ranked"])
    assert set(report.backends) == {"stub", "ranked"}
    info = report.backends["stub"]
    assert info["n_decided"] == 120
    assert info["n_abstained"] == 0
    assert info["aurc"] >= info["oracle_aurc"]
    assert info["excess_aurc"] >= 0.0
    # stub is perfectly confident (p=1.0) and right 70%: the curve's
    # full-coverage risk is 0.3.
    assert info["curve"][-1]["risk"] == pytest.approx(0.3)
    assert report.policy_threshold == pytest.approx(0.0)
    assert report.best_ranking() in {"stub", "ranked"}


def test_policy_threshold_point(gate_with_stub):
    policy = DecisionPolicy(minimum_probability=0.5)
    report = selective_evaluate(_dataset(), gate_with_stub, ["stub"],
                                policy=policy)
    point = report.backends["stub"]["policy_threshold_point"]
    assert point["threshold"] <= 0.5
    assert 0.0 < point["coverage"] <= 1.0


def test_report_queries(gate_with_stub):
    report = selective_evaluate(_dataset(), gate_with_stub, ["stub"])
    cov = report.coverage_at_risk("stub", 0.3)
    assert 0.0 < cov <= 1.0
    with pytest.raises(EvalError):
        report.coverage_at_risk("ghost", 0.3)
    with pytest.raises(EvalError):
        report.excess_aurc("ghost")


def test_all_abstained_rejected(gate_with_stub):
    from hugrgate.backend import Backend
    from hugrgate.errors import Abstention

    class Never(Backend):
        name = "never"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            raise Abstention("nope")

    gate_with_stub.register(Never())
    with pytest.raises(EvalError):
        selective_evaluate(_dataset(10), gate_with_stub, ["never"])


def test_empty_dataset_rejected(gate_with_stub):
    ds = _dataset(10)
    ds["items"] = []
    with pytest.raises(EvalError):
        selective_evaluate(ds, gate_with_stub, ["stub"])


def test_report_roundtrip(gate_with_stub):
    report = selective_evaluate(_dataset(), gate_with_stub, ["stub"])
    clone = SelectiveReport.from_dict(report.to_dict())
    assert clone.to_dict() == report.to_dict()
    assert clone.best_ranking() == report.best_ranking()
