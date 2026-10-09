"""Tests for slice 079 — online calibration."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration import CalibratorRegistry
from hugrgate.calibration.metrics import expected_calibration_error
from hugrgate.calibration.online import OnlineCalibrator
from hugrgate.errors import CalibrationError


def _phase(n: int, k: float, seed: int):
    """Scores = sigmoid(k*z), labels from true sigmoid(z)."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-k * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


def test_online_tracks_drift():
    # Phase 1: overconfident (k=2). Phase 2: underconfident (k=0.5).
    s1, y1 = _phase(600, 2.0, 1)
    s2, y2 = _phase(600, 0.5, 2)
    online = OnlineCalibrator(n_bins=10, decay=0.9)
    online.partial_fit(s1, y1)
    frozen = OnlineCalibrator(n_bins=10, decay=1.0).fit(s1, y1)
    for _ in range(6):
        online.partial_fit(s2, y2)
    cal_new = online.calibrate_batch(s2)
    cal_frozen = frozen.calibrate_batch(s2)
    ece_new = expected_calibration_error(y2, cal_new)
    ece_frozen = expected_calibration_error(y2, cal_frozen)
    assert ece_new < ece_frozen
    # Forgetting actually happened: effective history < cumulative count.
    assert online.effective_samples() < 600 + 6 * 600


def test_online_monotone_and_bounded():
    s, y = _phase(400, 2.0, 5)
    cal = OnlineCalibrator(n_bins=8).fit(s, y)
    grid = np.linspace(0.0, 1.0, 51)
    vals = cal.calibrate_batch(grid.tolist())
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))
    stats = cal.bin_stats()
    assert len(stats) == 8
    assert all(set(st) == {"bin", "weight", "positives", "rate"}
               for st in stats)


def test_online_params_round_trip():
    s, y = _phase(200, 2.0, 9)
    cal = OnlineCalibrator(n_bins=6, decay=0.95).fit(s, y)
    cal.partial_fit(s, y)
    back = OnlineCalibrator.from_params(cal.get_params())
    assert back.decay == pytest.approx(0.95)
    assert back.effective_samples() == pytest.approx(cal.effective_samples())
    for v in (0.05, 0.5, 0.95):
        assert back.calibrate(v) == pytest.approx(cal.calibrate(v))


def test_online_errors():
    cal = OnlineCalibrator()
    with pytest.raises(CalibrationError):
        cal.calibrate(0.5)
    with pytest.raises(CalibrationError):
        cal.partial_fit([], [])
    with pytest.raises(CalibrationError):
        OnlineCalibrator(n_bins=1)
    with pytest.raises(CalibrationError):
        OnlineCalibrator(decay=0.0)
    with pytest.raises(CalibrationError):
        OnlineCalibrator(decay=1.5)
    assert CalibratorRegistry.get("online") is OnlineCalibrator
