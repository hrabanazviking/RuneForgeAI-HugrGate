"""Slice 494 — calibration truth audit.

The ECE metric is audited against synthetic data with known true
probabilities: a perfect forecaster must score near zero, a
deliberately miscalibrated one must score clearly above zero, and
ECE must grow monotonically with miscalibration severity.
"""

from __future__ import annotations

import numpy as np

from hugrgate.calibration.metrics import expected_calibration_error
from hugrgate.gauntlet.calibration_audit import (
    overconfidence_map,
    run_calibration_audit,
    synthetic_bernoulli,
)


def test_synthetic_generator_reproducible():
    p1, y1 = synthetic_bernoulli(1000, seed=7)
    p2, y2 = synthetic_bernoulli(1000, seed=7)
    assert np.array_equal(p1, p2)
    assert np.array_equal(y1, y2)
    p3, _ = synthetic_bernoulli(1000, seed=8)
    assert not np.array_equal(p1, p3)
    # Labels track probabilities in aggregate.
    assert abs(y1.mean() - 0.5) < 0.05


def test_perfect_forecaster_ece_near_zero():
    p, y = synthetic_bernoulli(20_000, seed=494)
    ece = expected_calibration_error(y, p, 15)
    assert ece < 0.03, f"perfect forecaster ECE too high: {ece}"


def test_miscalibrated_forecaster_ece_high():
    p, y = synthetic_bernoulli(20_000, seed=494)
    q = overconfidence_map(1.5)(p)
    ece = expected_calibration_error(y, q, 15)
    assert ece > 0.04, f"miscalibration not detected: {ece}"


def test_ece_monotone_in_severity():
    p, y = synthetic_bernoulli(20_000, seed=494)
    eces = [expected_calibration_error(y, overconfidence_map(s)(p), 15)
            for s in (1.0, 1.25, 1.5)]
    assert eces[0] < eces[1] < eces[2], eces


def test_full_audit_passes():
    report = run_calibration_audit()
    assert report.passed, report.to_markdown()
    assert report.perfect_within_noise
    assert report.miscalibration_detected
    assert report.monotone
    assert len(report.perfect_bins) == 15


def test_audit_report_marks_failure_modes():
    from dataclasses import replace

    report = run_calibration_audit()
    bad = replace(report, ece_perfect=0.99)
    assert not bad.passed
    assert not bad.perfect_within_noise
    flat = replace(report, ece_by_severity={1.0: 0.5, 1.5: 0.1})
    assert not flat.monotone
    assert not flat.passed
