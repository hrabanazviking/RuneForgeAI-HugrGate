"""Tests for slice 096 — aleatoric uncertainty adapters."""

from __future__ import annotations

import math

import numpy as np
import pytest

from hugrgate.calibration.aleatoric import (
    AleatoricReport,
    bernoulli_noise,
    label_noise_estimate,
    noise_floor_report,
    predictive_entropy,
)
from hugrgate.errors import CalibrationError


def test_predictive_entropy():
    assert predictive_entropy({"a": 1.0}) == pytest.approx(0.0)
    assert predictive_entropy({"a": 0.5, "b": 0.5}) == pytest.approx(
        math.log(2))
    assert predictive_entropy({"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}
                              ) == pytest.approx(math.log(4))
    with pytest.raises(CalibrationError):
        predictive_entropy({})
    with pytest.raises(CalibrationError):
        predictive_entropy({"a": -0.5, "b": 1.5})


def test_bernoulli_noise():
    assert bernoulli_noise(0.0) == 0.0
    assert bernoulli_noise(1.0) == 0.0
    assert bernoulli_noise(0.5) == pytest.approx(0.25)
    assert bernoulli_noise(0.9) == pytest.approx(bernoulli_noise(0.1))
    with pytest.raises(CalibrationError):
        bernoulli_noise(1.5)


def test_label_noise_estimate():
    rng = np.random.default_rng(0)
    # Pure noise: scores carry no signal → ~0.25.
    s = rng.random(2000).tolist()
    y = (rng.random(2000) < 0.5).astype(int).tolist()
    assert label_noise_estimate(s, y) == pytest.approx(0.25, abs=0.02)
    # Perfect separation: scores 0/1 match labels → ~0.
    s2 = [0.0] * 1000 + [1.0] * 1000
    y2 = [0] * 1000 + [1] * 1000
    assert label_noise_estimate(s2, y2) == pytest.approx(0.0, abs=1e-9)
    # Partial signal lands in between.
    z = rng.normal(0, 1, 2000)
    p = 1.0 / (1.0 + np.exp(-z))
    y3 = (rng.random(2000) < p).astype(int).tolist()
    mid = label_noise_estimate(p.tolist(), y3)
    assert 0.05 < mid < 0.25
    with pytest.raises(CalibrationError):
        label_noise_estimate([], [])


def test_noise_floor_report():
    rng = np.random.default_rng(1)
    s = rng.random(500).tolist()
    y = (rng.random(500) < 0.5).astype(int).tolist()
    rep = noise_floor_report(s, y, n_bins=5)
    assert isinstance(rep, AleatoricReport)
    d = rep.as_dict()
    assert d["adapter"] == "label-noise"
    assert len(d["details"]["bins"]) == 5
    assert d["details"]["n_samples"] == 500
    assert d["value"] == pytest.approx(0.25, abs=0.03)
