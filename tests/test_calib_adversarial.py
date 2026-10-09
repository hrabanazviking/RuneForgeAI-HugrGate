"""Tests for slice 098 — calibration adversarial tests."""

from __future__ import annotations

import json

import numpy as np
import pytest

from hugrgate.calibration.adversarial import (
    StressReport,
    bias_shift_attack,
    label_flip_attack,
    overconfidence_attack,
    stress_test,
    underconfidence_attack,
)
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.calibration.temperature import TemperatureCalibrator
from hugrgate.errors import CalibrationError


def _data(n: int = 600, seed: int = 0):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.2, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-2.0 * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


def test_attack_shapes():
    s, y = _data()
    over = overconfidence_attack(s, 0.3)
    assert all(0.0 <= v <= 1.0 for v in over)
    # Overconfidence pushes mass toward extremes.
    assert sum(1 for v in over if v > 0.9) >= sum(1 for v in s if v > 0.9)
    under = underconfidence_attack(s, 1.0)
    assert all(v == pytest.approx(0.5) for v in under)
    assert overconfidence_attack(s, 0.0) == pytest.approx(s)
    shifted = bias_shift_attack(s, 0.1)
    assert all(b >= a - 1e-12 for a, b in zip(s, shifted))
    flipped = label_flip_attack(y, 0.5, seed=1)
    assert abs(sum(flipped) / len(flipped) - 0.5) < 0.1
    assert label_flip_attack(y, 0.0, seed=1) == y
    for bad in (lambda: overconfidence_attack(s, 1.5),
                lambda: underconfidence_attack(s, -0.1),
                lambda: label_flip_attack(y, 2.0),
                lambda: bias_shift_attack(s, 2.0),
                lambda: label_flip_attack([0, 2], 0.1)):
        with pytest.raises(CalibrationError):
            bad()


def test_stress_test_degrades_under_attack():
    s, y = _data()
    report = stress_test(PlattCalibrator, s, y)
    assert isinstance(report, StressReport)
    assert report.calibrator_name == "platt"
    assert len(report.attacks) == 5
    # Brier is a proper scoring rule: attacks never improve it (up to noise).
    assert all(a["brier_degradation"] >= -1e-9 for a in report.attacks)
    # Strong attacks strictly hurt a fitted map on at least one metric.
    assert report.worst_ece_degradation() > 0.01
    d = report.as_dict()
    json.dumps(d)
    assert d["baseline"]["ece"] >= 0.0


def test_stress_test_custom_attacks_and_factories():
    s, y = _data()
    report = stress_test(
        TemperatureCalibrator, s, y,
        attacks={"mild": lambda ss, yy: (bias_shift_attack(ss, 0.02), yy)})
    assert [a["name"] for a in report.attacks] == ["mild"]
    assert report.attacks[0]["brier_degradation"] >= -1e-9
    with pytest.raises(CalibrationError):
        stress_test(lambda: "nope", s, y)
