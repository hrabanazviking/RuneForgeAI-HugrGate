"""Tests for slice 080 — sliding-window calibration."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration import CalibratorRegistry
from hugrgate.calibration.metrics import expected_calibration_error
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.calibration.window import SlidingWindowCalibrator
from hugrgate.errors import CalibrationError


def _phase(n: int, k: float, seed: int):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-k * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


def test_window_evicts_and_refits():
    s1, y1 = _phase(300, 2.0, 1)
    s2, y2 = _phase(300, 0.5, 2)
    sw = SlidingWindowCalibrator(PlattCalibrator, window_size=300,
                                 refit_every=100, min_samples=20)
    sw.partial_fit(s1, y1)   # one refit at the end of the bulk batch
    assert sw.refit_count == 1
    assert sw.window_fill == 300
    first_span = sw.window_span
    sw.partial_fit(s2, y2)   # window now holds only phase-2 data
    assert sw.refit_count == 2
    assert sw.window_fill == 300
    assert sw.window_span != first_span
    # After the window slid fully onto phase 2, ECE on phase-2 data beats a
    # frozen phase-1 Platt fit.
    frozen = PlattCalibrator().fit(s1, y1)
    ece_new = expected_calibration_error(y2, sw.calibrate_batch(s2))
    ece_old = expected_calibration_error(
        y2, [frozen.calibrate(v) for v in s2])
    assert ece_new < ece_old


def test_window_params_round_trip():
    s, y = _phase(120, 2.0, 3)
    sw = SlidingWindowCalibrator(PlattCalibrator, window_size=100,
                                 refit_every=60).fit(s, y)
    back = SlidingWindowCalibrator.from_params(sw.get_params())
    assert back.window_fill == sw.window_fill == 100
    assert back.refit_count == sw.refit_count
    for v in (0.2, 0.8):
        assert back.calibrate(v) == pytest.approx(sw.calibrate(v))
    assert CalibratorRegistry.get("sliding-window") is SlidingWindowCalibrator


def test_window_errors_and_degenerate_windows():
    sw = SlidingWindowCalibrator(PlattCalibrator, min_samples=20)
    with pytest.raises(CalibrationError):
        sw.calibrate(0.5)  # never fitted
    # Single-class window: refit refuses, old map (none) stays absent.
    assert sw.partial_fit([0.9] * 30, [1] * 30).refit() is False
    with pytest.raises(CalibrationError):
        sw.calibrate(0.5)
    with pytest.raises(CalibrationError):
        SlidingWindowCalibrator(PlattCalibrator, window_size=1)
    with pytest.raises(CalibrationError):
        SlidingWindowCalibrator(lambda: "nope")
    with pytest.raises(CalibrationError):
        SlidingWindowCalibrator(PlattCalibrator).fit([0.5] * 5, [1] * 5)
