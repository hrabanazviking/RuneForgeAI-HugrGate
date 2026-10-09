"""Tests for slice 097 — calibration visualization data."""

from __future__ import annotations

import json

import numpy as np
import pytest

from hugrgate.calibration.metrics import expected_calibration_error
from hugrgate.calibration.risk_coverage import risk_coverage_curve
from hugrgate.calibration.selective import selective_curve
from hugrgate.calibration.viz import (
    calibration_dashboard,
    confidence_histogram,
    per_class_ece_bars,
    reliability_curve_data,
    risk_coverage_points,
    selective_curve_points,
)
from hugrgate.errors import CalibrationError


def _data(n: int = 500, seed: int = 0):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, (n, 3))
    p = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
    names = ["a", "b", "c"]
    probas = [dict(zip(names, row, strict=True)) for row in p]
    labels = [names[int((rng.random() < row.cumsum()).argmax())]
              for row in p]
    return labels, probas


def test_reliability_curve_data():
    rng = np.random.default_rng(1)
    y = (rng.random(300) < 0.6).astype(int).tolist()
    p = rng.random(300).tolist()
    payload = reliability_curve_data(y, p, n_bins=8)
    assert len(payload["points"]) == 8
    assert payload["ece"] == pytest.approx(
        expected_calibration_error(y, p, 8))
    assert payload["diagonal"] == [{"x": 0.0, "y": 0.0},
                                  {"x": 1.0, "y": 1.0}]
    json.dumps(payload)  # JSON-serializable
    with pytest.raises(ValueError):
        reliability_curve_data([], [])


def test_confidence_histogram():
    _labels, probas = _data()
    h = confidence_histogram(probas, n_bins=5)
    assert len(h["bins"]) == 5
    assert sum(b["count"] for b in h["bins"]) == 500
    assert abs(sum(b["fraction"] for b in h["bins"]) - 1.0) < 1e-9
    json.dumps(h)
    with pytest.raises(CalibrationError):
        confidence_histogram([])


def test_per_class_ece_bars():
    labels, probas = _data()
    bars = per_class_ece_bars(labels, probas)
    assert bars["n_classes"] == 3
    assert {b["class"] for b in bars["bars"]} == {"a", "b", "c"}
    assert all(b["ece"] >= 0.0 for b in bars["bars"])
    json.dumps(bars)
    with pytest.raises(CalibrationError):
        per_class_ece_bars(labels, probas[:10])


def test_curve_points_passthrough():
    rng = np.random.default_rng(2)
    conf = rng.random(200).tolist()
    correct = (rng.random(200) < 0.7).astype(int).tolist()
    losses = [1 - c for c in correct]
    sc = selective_curve_points(selective_curve(conf, correct))
    rc = risk_coverage_points(risk_coverage_curve(conf, losses))
    assert len(sc["points"]) == 50 and len(rc["points"]) == 50
    json.dumps(sc)
    json.dumps(rc)


def test_calibration_dashboard():
    labels, probas = _data()
    dash = calibration_dashboard(labels, probas)
    assert set(dash) == {"summary", "reliability", "confidence_histogram",
                        "per_class_ece"}
    assert dash["summary"]["n_samples"] == 500
    assert 0.0 <= dash["summary"]["accuracy"] <= 1.0
    json.dumps(dash)
    with pytest.raises(CalibrationError):
        calibration_dashboard([], [])
