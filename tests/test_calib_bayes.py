"""Tests for slice 081 — Bayesian calibration research adapter."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration import CalibratorRegistry
from hugrgate.calibration.bayes import (
    BetaBinomialCalibrator,
    _betai,
    beta_quantile,
)
from hugrgate.calibration.metrics import expected_calibration_error
from hugrgate.errors import CalibrationError


def _miscalibrated(n: int = 500, seed: int = 4):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-2.0 * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


def test_beta_incomplete_sanity():
    # Against known values: I_0.5(2, 2) = 0.5; median of Beta(2,5) ≈ 0.264.
    assert _betai(2.0, 2.0, 0.5) == pytest.approx(0.5, abs=1e-9)
    assert beta_quantile(0.5, 2.0, 5.0) == pytest.approx(0.264, abs=1e-3)
    assert beta_quantile(0.05, 2.0, 5.0) < beta_quantile(0.95, 2.0, 5.0)
    with pytest.raises(ValueError):
        beta_quantile(0.0, 1.0, 1.0)


def test_betabinomial_improves_ece():
    s, y = _miscalibrated()
    cal = BetaBinomialCalibrator(n_bins=10).fit(s, y)
    out = cal.calibrate_batch(s)
    assert expected_calibration_error(y, out) < expected_calibration_error(y, s)


def test_credible_interval_properties():
    s, y = _miscalibrated(n=120)
    cal = BetaBinomialCalibrator(n_bins=10).fit(s, y)
    lo, hi = cal.credible_interval(0.5, level=0.9)
    mean = cal.calibrate(0.5)
    assert lo <= mean <= hi
    # More data → narrower interval: compare a data-rich vs data-poor bin.
    widths = []
    for v in np.linspace(0.05, 0.95, 10):
        a, b = cal.credible_interval(float(v))
        widths.append(b - a)
    assert max(widths) > min(widths)
    # Wide interval on (nearly) empty bins: uniform prior → 90% CI ≈ [0.05, 0.95].
    empty = BetaBinomialCalibrator(n_bins=10).fit([0.99] * 20, [1] * 10 + [0] * 10)
    lo0, hi0 = empty.credible_interval(0.05)
    assert hi0 - lo0 > 0.8
    with pytest.raises(CalibrationError):
        cal.credible_interval(0.5, level=1.5)


def test_betabinomial_params_round_trip():
    s, y = _miscalibrated()
    cal = BetaBinomialCalibrator(n_bins=8, prior_a=2.0, prior_b=2.0).fit(s, y)
    back = BetaBinomialCalibrator.from_params(cal.get_params())
    for v in (0.1, 0.5, 0.9):
        assert back.calibrate(v) == pytest.approx(cal.calibrate(v))
        assert back.credible_interval(v) == pytest.approx(
            cal.credible_interval(v))
    assert CalibratorRegistry.get("beta-binomial") is BetaBinomialCalibrator


def test_betabinomial_errors():
    with pytest.raises(CalibrationError):
        BetaBinomialCalibrator(n_bins=1)
    with pytest.raises(CalibrationError):
        BetaBinomialCalibrator(prior_a=0.0)
    cal = BetaBinomialCalibrator()
    with pytest.raises(CalibrationError):
        cal.calibrate(0.5)
    with pytest.raises(CalibrationError):
        cal.fit([], [])
