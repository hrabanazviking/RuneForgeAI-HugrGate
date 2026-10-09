"""Tests for slice 077 — per-class calibration."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration import CalibratorRegistry
from hugrgate.calibration.perclass import (
    PerClassCalibrator,
    _ConstantCalibrator,
    build_profile,
)
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.calibration.profiles import CalibrationProfile
from hugrgate.errors import CalibrationError


def _multiclass(n: int = 600, seed: int = 11):
    """3-class data, each class overconfident on its own scores."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, (n, 3))
    p_true = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
    raw = np.exp(2.0 * z)
    raw = raw / raw.sum(axis=1, keepdims=True)
    labels = [("abc"[i]) for i in
              (rng.random(n)[:, None] < p_true.cumsum(axis=1)).argmax(axis=1)]
    probas = [dict(zip("abc", row, strict=True)) for row in raw]
    return probas, labels


def test_perclass_improves_each_class():
    probas, labels = _multiclass()
    pc = PerClassCalibrator(PlattCalibrator).fit(probas, labels)
    assert pc.classes == ["a", "b", "c"]
    for cls_name, m in pc.per_class_metrics.items():
        assert m["brier_after"] <= m["brier_before"] + 1e-9, cls_name
        assert m["fallback"] == 0.0
    cal = pc.calibrate_batch(probas)
    for d in cal:
        assert abs(sum(d.values()) - 1.0) < 1e-9
        assert set(d) == {"a", "b", "c"}


def test_perclass_missing_class_fallback():
    probas, labels = _multiclass()
    # Declare a fourth class "d" never seen in the fit data.
    pc = PerClassCalibrator(PlattCalibrator).fit(probas, labels,
                                                 classes=["a", "b", "c", "d"])
    assert pc.per_class_metrics["d"]["fallback"] == 1.0
    d = pc.calibrate_dist({"a": 0.7, "b": 0.2, "c": 0.1, "d": 0.0})
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert d["d"] == 0.0  # prior 0 → stays 0 after renormalization


def test_perclass_profile_round_trip():
    probas, labels = _multiclass()
    pc = PerClassCalibrator(PlattCalibrator).fit(
        probas, labels, classes=["a", "b", "c", "d"])
    profile = build_profile("perclass-test", pc, backend_name="rules")
    assert profile.calibrator_name == "platt"
    assert profile.classes == ["a", "b", "c", "d"]
    # Round-trip through JSON, then rebuild the units (exercises the
    # __fallback__ path added to CalibrationProfile.build_calibrators).
    profile2 = CalibrationProfile.from_json(profile.to_json())
    units = profile2.build_calibrators()
    assert isinstance(units["d"], _ConstantCalibrator)
    assert isinstance(units["a"], PlattCalibrator)
    pc2 = PerClassCalibrator.from_profile_params(
        PlattCalibrator, profile2.calibrator_params)
    d1 = pc.calibrate_dist(probas[0])
    d2 = pc2.calibrate_dist(probas[0])
    for k in d1:
        assert d1[k] == pytest.approx(d2[k])


def test_perclass_errors():
    pc = PerClassCalibrator(PlattCalibrator)
    with pytest.raises(CalibrationError):
        pc.calibrate_dist({"a": 1.0})
    with pytest.raises(CalibrationError):
        pc.fit([], [])
    with pytest.raises(CalibrationError):
        pc.fit([{"a": 1.0}], ["a", "b"])
    with pytest.raises(CalibrationError):
        PerClassCalibrator(lambda: 42)


def test_constant_prior_registered():
    cls = CalibratorRegistry.get("constant-prior")
    assert cls is _ConstantCalibrator
    cal = cls.from_params({"prior": 0.3})
    assert cal.calibrate(0.99) == pytest.approx(0.3)
    with pytest.raises(CalibrationError):
        _ConstantCalibrator(1.5)
