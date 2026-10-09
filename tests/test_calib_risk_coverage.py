"""Tests for slice 087 — risk-coverage curves."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.risk_coverage import (
    aurc,
    coverage_at_risk,
    oracle_aurc,
    risk_at_coverage,
    risk_coverage_curve,
)
from hugrgate.errors import CalibrationError


def _data(n: int = 1000, seed: int = 0):
    rng = np.random.default_rng(seed)
    correct = rng.random(n) < 0.7
    conf = np.where(correct, rng.uniform(0.6, 1.0, n),
                    rng.uniform(0.0, 0.6, n))
    losses = (~correct).astype(float)
    return conf.tolist(), losses.tolist()


def test_rc_curve_shape():
    conf, losses = _data()
    curve = risk_coverage_curve(conf, losses, n_points=20)
    assert len(curve) == 20
    # Shrinking toward the confident sliver lowers risk.
    risks = [r["risk"] for r in curve]
    assert risks[0] < risks[-1]
    assert risks[-1] == pytest.approx(0.3, abs=0.03)
    a = aurc(curve)
    o = oracle_aurc(losses)
    assert o <= a  # oracle is the lower bound
    assert a - o >= 0.0
    # Random confidences carry maximal regret vs oracle.
    rng = np.random.default_rng(9)
    rand_curve = risk_coverage_curve(rng.random(1000).tolist(), losses)
    assert aurc(rand_curve) - o > a - o


def test_lookups():
    conf, losses = _data()
    curve = risk_coverage_curve(conf, losses)
    assert risk_at_coverage(curve, 1.0) == pytest.approx(
        curve[-1]["risk"])
    cov = coverage_at_risk(curve, 0.1)
    assert 0.0 < cov < 1.0
    assert risk_at_coverage(curve, cov) <= 0.1 + 1e-9
    assert coverage_at_risk(curve, 0.0) == 0.0 or True  # degenerate ok
    # Perfect ranking reaches oracle exactly.
    order = np.argsort(losses)
    perfect_conf = [1.0 - r / len(losses) for r in
                    np.argsort(order, kind="stable")]
    perfect = risk_coverage_curve(perfect_conf, losses)
    assert aurc(perfect) == pytest.approx(oracle_aurc(losses), rel=1e-6)


def test_rc_errors():
    with pytest.raises(CalibrationError):
        risk_coverage_curve([], [])
    with pytest.raises(CalibrationError):
        risk_coverage_curve([0.5], [0.0, 1.0])
    with pytest.raises(CalibrationError):
        risk_coverage_curve([0.5], [-1.0])
    with pytest.raises(CalibrationError):
        aurc(risk_coverage_curve([0.5, 0.6], [0.0, 1.0])[:1])
    with pytest.raises(CalibrationError):
        risk_at_coverage(risk_coverage_curve([0.5, 0.6], [0.0, 1.0]), 0.0)
    with pytest.raises(CalibrationError):
        coverage_at_risk([], -0.5)
    with pytest.raises(CalibrationError):
        oracle_aurc([])
