"""Tests for slice 089 — calibration under imbalance."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.imbalance import (
    ImbalanceReport,
    fit_balanced,
    rebalance,
    saerens_prior_correction,
    stratified_metrics,
)
from hugrgate.calibration.metrics import brier_score
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.errors import CalibrationError


def _gen(n: int, rate: float, k: float, seed: int):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    p = 1.0 / (1.0 + np.exp(-z))
    s = 1.0 / (1.0 + np.exp(-k * z))
    y = (rng.random(n) < p).astype(int)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    npos = int(n * rate)
    take = np.concatenate([rng.choice(pos, npos, replace=True),
                           rng.choice(neg, n - npos, replace=True)])
    rng.shuffle(take)
    return s[take].tolist(), y[take].tolist()


def test_rebalance_hits_target_rate():
    s, y = _gen(1000, 0.1, 2.0, 1)
    rs, ry = rebalance(s, y, target_rate=0.5, seed=7)
    assert len(rs) == len(s) == 1000
    assert sum(ry) / len(ry) == pytest.approx(0.5, abs=0.02)
    rs2, ry2 = rebalance(s, y, target_rate=0.5, seed=7)
    assert rs2 == rs and ry2 == ry  # seeded → deterministic
    with pytest.raises(CalibrationError):
        rebalance(s, y, target_rate=0.0)
    with pytest.raises(CalibrationError):
        rebalance([0.5] * 10, [0] * 10)


def test_saerens_correction_properties():
    # Identity when priors match.
    assert saerens_prior_correction(0.7, 0.3, 0.3) == pytest.approx(0.7)
    # Shifting to a higher deployment prior raises probabilities.
    assert saerens_prior_correction(0.5, 0.5, 0.8) > 0.5
    assert saerens_prior_correction(0.5, 0.5, 0.2) < 0.5
    # Monotone in p_cal, bounded in [0, 1].
    vals = [saerens_prior_correction(p / 100, 0.2, 0.6) for p in range(101)]
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert all(b >= a for a, b in zip(vals, vals[1:]))
    with pytest.raises(CalibrationError):
        saerens_prior_correction(0.5, 0.0, 0.5)
    with pytest.raises(CalibrationError):
        saerens_prior_correction(1.5, 0.5, 0.5)


def test_fit_balanced_end_to_end():
    tr_s, tr_y = _gen(3000, 0.10, 2.0, 1)
    dep_s, dep_y = _gen(2000, 0.40, 2.0, 2)
    cal, report = fit_balanced(PlattCalibrator, tr_s, tr_y,
                               target_rate=0.5, seed=3, deploy_prior=0.40)
    assert isinstance(report, ImbalanceReport)
    assert report.as_dict()["base_rate"] == pytest.approx(0.10, abs=0.01)
    assert report.correction_applied is True
    raw = [cal.calibrate(v) for v in dep_s]
    corr = [saerens_prior_correction(p, 0.5, 0.40) for p in raw]
    assert brier_score(dep_y, corr) < brier_score(dep_y, raw)
    with pytest.raises(CalibrationError):
        fit_balanced(lambda: "nope", tr_s, tr_y)


def test_stratified_metrics():
    s, y = _gen(1000, 0.3, 2.0, 5)
    sm = stratified_metrics(y, s)
    assert set(sm) == {"positive", "negative", "overall"}
    assert sm["positive"]["n"] + sm["negative"]["n"] == 1000
    assert sm["overall"]["n"] == 1000
    for stratum in sm.values():
        assert stratum["brier"] >= 0.0
    with pytest.raises(CalibrationError):
        stratified_metrics([1, 0], [0.5])
    with pytest.raises(CalibrationError):
        stratified_metrics([], [])
