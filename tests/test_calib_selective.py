"""Tests for slice 086 — selective prediction curves."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.selective import (
    accuracy_at_coverage,
    area_under_selective_curve,
    coverage_at_accuracy,
    selective_curve,
)
from hugrgate.errors import CalibrationError


def _confident_right(n: int = 1000, seed: int = 0):
    """Confidence tracks correctness: right answers are confident."""
    rng = np.random.default_rng(seed)
    correct = rng.random(n) < 0.7
    conf = np.where(correct,
                    rng.uniform(0.6, 1.0, n),
                    rng.uniform(0.0, 0.6, n))
    return conf.tolist(), correct.astype(int).tolist()


def test_selective_curve_monotone_quality():
    conf, correct = _confident_right()
    curve = selective_curve(conf, correct, n_points=20)
    assert len(curve) == 20
    covs = [r["coverage"] for r in curve]
    assert covs == sorted(covs)
    assert covs[0] > 0 and covs[-1] == pytest.approx(1.0)
    # Keeping only the most confident sliver beats answering everything.
    assert curve[0]["accuracy"] > curve[-1]["accuracy"]
    assert curve[-1]["accuracy"] == pytest.approx(0.7, abs=0.03)


def test_area_and_lookups():
    conf, correct = _confident_right()
    curve = selective_curve(conf, correct)
    ausc = area_under_selective_curve(curve)
    assert 0.7 < ausc <= 1.0
    # Perfect classifier: area 1, full coverage at accuracy 1.
    perfect = selective_curve([0.9] * 100, [1] * 100)
    assert area_under_selective_curve(perfect) == pytest.approx(1.0)
    assert coverage_at_accuracy(perfect, 1.0) == pytest.approx(1.0)
    # Lookup consistency on the realistic curve.
    assert accuracy_at_coverage(curve, 1.0) == pytest.approx(
        curve[-1]["accuracy"])
    cov = coverage_at_accuracy(curve, 0.9)
    assert 0.0 < cov < 1.0
    assert accuracy_at_coverage(curve, cov) >= 0.9 - 1e-9


def test_selective_errors():
    with pytest.raises(CalibrationError):
        selective_curve([], [])
    with pytest.raises(CalibrationError):
        selective_curve([0.5], [1, 0])
    with pytest.raises(CalibrationError):
        selective_curve([1.5], [1])
    with pytest.raises(CalibrationError):
        selective_curve([0.5], [2])
    with pytest.raises(CalibrationError):
        area_under_selective_curve(selective_curve([0.5], [1])[:1])
    with pytest.raises(CalibrationError):
        accuracy_at_coverage(selective_curve([0.5, 0.6], [1, 0]), 0.0)
