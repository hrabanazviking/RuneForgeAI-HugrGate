"""Tests for slice 083 — conformal regression."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.conformal_regression import ConformalRegressor
from hugrgate.errors import CalibrationError


def _data(n: int, seed: int, hetero: bool = False):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    sigma = (0.5 + np.abs(x)) if hetero else np.full(n, 1.0)
    y = 2.0 * x + rng.normal(0, sigma)
    y_pred = 2.0 * x  # unbiased point predictor
    return y_pred.tolist(), y.tolist(), sigma.tolist()


def test_conformal_regression_coverage():
    yp_cal, y_cal, _ = _data(1500, 1)
    yp_test, y_test, _ = _data(3000, 2)
    cr = ConformalRegressor(alpha=0.1).fit(yp_cal, y_cal)
    cov = cr.empirical_coverage(yp_test, y_test)
    assert cov >= 0.9 - 0.02
    assert cr.mean_width(yp_test) > 0
    lo, hi = cr.predict_interval(1.0)
    assert lo < 1.0 < hi


def test_conformal_regression_weighted_adapts():
    yp_cal, y_cal, d_cal = _data(1500, 3, hetero=True)
    yp_test, y_test, d_test = _data(2000, 4, hetero=True)
    cr = ConformalRegressor(alpha=0.1).fit(yp_cal, y_cal, difficulty=d_cal)
    cov = cr.empirical_coverage(yp_test, y_test, difficulty=d_test)
    assert cov >= 0.9 - 0.03
    easy = cr.predict_interval(0.0, difficulty=0.5)
    hard = cr.predict_interval(0.0, difficulty=2.5)
    assert (hard[1] - hard[0]) > (easy[1] - easy[0])
    # Weighted fit refuses unweighted prediction and vice versa.
    with pytest.raises(CalibrationError):
        cr.predict_interval(0.0)
    plain = ConformalRegressor(alpha=0.1).fit(yp_cal, y_cal)
    with pytest.raises(CalibrationError):
        plain.predict_interval(0.0, difficulty=1.0)


def test_conformal_regression_errors():
    cr = ConformalRegressor()
    with pytest.raises(CalibrationError):
        cr.predict_interval(0.0)
    with pytest.raises(CalibrationError):
        cr.fit([], [])
    with pytest.raises(CalibrationError):
        cr.fit([1.0, 2.0], [1.0])
    with pytest.raises(CalibrationError):
        cr.fit([1.0, float("nan")], [1.0, 2.0])
    with pytest.raises(CalibrationError):
        cr.fit([1.0, 2.0], [1.0, 2.0], difficulty=[1.0, 0.0])
    with pytest.raises(CalibrationError):
        ConformalRegressor(alpha=2.0)
