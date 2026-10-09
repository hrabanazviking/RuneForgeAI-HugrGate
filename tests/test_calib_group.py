"""Tests for slice 078 — group calibration."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.group import GroupCalibrator
from hugrgate.calibration.metrics import expected_calibration_error
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.errors import CalibrationError


def _two_groups(n: int = 500, seed: int = 21):
    """Group A overconfident, group B underconfident — opposite biases."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores, groups = [], []
    for i in range(n):
        g = "A" if i % 2 == 0 else "B"
        k = 2.0 if g == "A" else 0.5
        scores.append(float(1.0 / (1.0 + np.exp(-k * z[i]))))
        groups.append(g)
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores, labels, groups


def test_group_calibration_beats_global():
    s, y, g = _two_groups()
    gc = GroupCalibrator(PlattCalibrator).fit(s, y, g)
    assert gc.groups == ["A", "B"]
    cal = gc.calibrate_batch(s, g)
    per_group_ece = {}
    for grp in ("A", "B"):
        idx = [i for i, gg in enumerate(g) if gg == grp]
        per_group_ece[grp] = expected_calibration_error(
            [y[i] for i in idx], [cal[i] for i in idx])
    # A single global Platt fit leaves a visible group gap; per-group fits
    # close it.
    glob = PlattCalibrator().fit(s, y)
    glob_cal = [glob.calibrate(v) for v in s]
    glob_gap = abs(
        expected_calibration_error([y[i] for i in range(len(y)) if g[i] == "A"],
                                   [glob_cal[i] for i in range(len(y)) if g[i] == "A"]) -
        expected_calibration_error([y[i] for i in range(len(y)) if g[i] == "B"],
                                   [glob_cal[i] for i in range(len(y)) if g[i] == "B"]))
    group_gap = abs(per_group_ece["A"] - per_group_ece["B"])
    assert group_gap < glob_gap
    assert gc.disparity() == pytest.approx(group_gap)


def test_group_unknown_group_uses_global():
    s, y, g = _two_groups()
    gc = GroupCalibrator(PlattCalibrator).fit(s, y, g)
    v = gc.calibrate(0.8, "never-seen")
    assert 0.0 <= v <= 1.0
    params = gc.get_params()
    assert set(params["groups"]) == {"A", "B"}
    assert params["group_metrics"]["A"]["mode"] == "fitted"


def test_group_small_group_shares_global():
    s = [0.1, 0.9] * 60
    y = [0, 1] * 60
    g = ["big"] * 117 + ["tiny"] * 3
    gc = GroupCalibrator(PlattCalibrator, min_group_samples=20).fit(s, y, g)
    assert gc.group_metrics["tiny"]["mode"] == "global-shared"
    assert gc.calibrate(0.5, "tiny") == pytest.approx(
        gc.calibrate(0.5, "nope"))


def test_group_errors():
    gc = GroupCalibrator(PlattCalibrator)
    with pytest.raises(CalibrationError):
        gc.calibrate(0.5, "A")
    with pytest.raises(CalibrationError):
        gc.disparity()
    s, y, g = _two_groups()
    with pytest.raises(CalibrationError):
        gc.fit(s, y, g[:10])
    with pytest.raises(CalibrationError):
        gc.fit([], [], [])
    with pytest.raises(CalibrationError):
        GroupCalibrator(lambda: 1)
