"""Tests for slice 088 — calibration under drift."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.drift import CalibrationDriftMonitor
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.errors import CalibrationError


def _batch(n: int, k: float, seed: int, shift: float = 0.0):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, n)
    p_true = 1.0 / (1.0 + np.exp(-(z + shift)))
    scores = 1.0 / (1.0 + np.exp(-k * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


@pytest.fixture()
def phase1_calibrator():
    s0, y0 = _batch(2000, 2.0, 999)
    return PlattCalibrator().fit(s0, y0)


def _calibrated(cal, n, k, seed, shift=0.0):
    s, y = _batch(n, k, seed, shift)
    return [cal.calibrate(v) for v in s], y


def test_monitor_quiet_when_stable(phase1_calibrator):
    mon = CalibrationDriftMonitor(baseline_batches=5)
    for i in range(12):
        s, y = _calibrated(phase1_calibrator, 500, 2.0, 100 + i)
        row = mon.observe(s, y)
        assert row["alarmed"] == 0.0
    assert not mon.alarmed
    assert mon.recommend() == "keep"
    assert mon.batches_seen == 12
    stats = mon.baseline_stats()
    assert stats["mean_brier"] > 0 and stats["std_brier"] >= 1e-3


def test_monitor_alarms_on_drift(phase1_calibrator):
    mon = CalibrationDriftMonitor(baseline_batches=5)
    for i in range(5):
        s, y = _calibrated(phase1_calibrator, 500, 2.0, 200 + i)
        mon.observe(s, y)
    assert mon.recommend() == "keep"
    # Drift: prior shift makes the phase-1 map systematically wrong.
    for i in range(6):
        s, y = _calibrated(phase1_calibrator, 500, 2.0, 300 + i, shift=-1.5)
        mon.observe(s, y)
    assert mon.alarmed
    assert mon.alarm_batch is not None and mon.alarm_batch >= 5
    assert mon.alarm_metric in ("brier", "ece")
    assert mon.recommend() == "recalibrate"
    rep = mon.report().as_dict()
    assert rep["alarmed"] is True
    assert rep["recommendation"] == "recalibrate"
    assert len(rep["history"]) == 11
    mon.reset_alarm()
    assert not mon.alarmed and mon.recommend() == "keep"


def test_recalibration_clears_the_alarm():
    # End-to-end: drift → alarm → refit on new data → quiet again.
    s0, y0 = _batch(2000, 2.0, 999)
    cal = PlattCalibrator().fit(s0, y0)
    mon = CalibrationDriftMonitor(baseline_batches=5)
    for i in range(5):
        s, y = _calibrated(cal, 500, 2.0, 200 + i)
        mon.observe(s, y)
    new_s, new_y = [], []
    for i in range(6):
        s, y = _batch(500, 2.0, 300 + i, shift=-1.5)
        new_s += s
        new_y += y
        mon.observe([cal.calibrate(v) for v in s], y)
    assert mon.alarmed
    # Recalibrate on the new regime and re-arm.
    cal = PlattCalibrator().fit(new_s, new_y)
    mon.reset_alarm()
    for i in range(6):
        s, y = _calibrated(cal, 500, 2.0, 400 + i, shift=-1.5)
        row = mon.observe(s, y)
        assert row["alarmed"] == 0.0
    assert mon.recommend() == "keep"


def test_monitor_errors():
    with pytest.raises(CalibrationError):
        CalibrationDriftMonitor(baseline_batches=1)
    with pytest.raises(CalibrationError):
        CalibrationDriftMonitor(k=0.0)
    with pytest.raises(CalibrationError):
        CalibrationDriftMonitor(min_std=-1.0)
    mon = CalibrationDriftMonitor(baseline_batches=4)
    with pytest.raises(CalibrationError):
        mon.baseline_stats()
    with pytest.raises(CalibrationError):
        mon.control_limits()
    with pytest.raises(CalibrationError):
        mon.observe([], [])
    with pytest.raises(CalibrationError):
        mon.observe([0.5], [1, 0])
