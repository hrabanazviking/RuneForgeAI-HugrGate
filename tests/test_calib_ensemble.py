"""Tests for slice 093 — calibration ensemble."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration import CalibratorRegistry
from hugrgate.calibration.ensemble import CalibratorEnsemble
from hugrgate.calibration.isotonic import IsotonicCalibrator
from hugrgate.calibration.metrics import brier_score
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.calibration.temperature import TemperatureCalibrator
from hugrgate.errors import CalibrationError


def _miscalibrated(n: int = 500, seed: int = 7):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.2, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-2.0 * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


def test_ensemble_jensen_bound():
    # Brier(convex combo) ≤ mean of member Briers (Jensen).
    s, y = _miscalibrated()
    ens = CalibratorEnsemble().fit(s, y)
    assert ens.member_names == ["platt", "isotonic", "temperature"]
    ens_brier = brier_score(y, ens.calibrate_batch(s))
    member_briers = []
    for cls in (PlattCalibrator, IsotonicCalibrator, TemperatureCalibrator):
        cal = cls().fit(s, y)
        member_briers.append(brier_score(y, cal.calibrate_batch(s)))
    assert ens_brier <= sum(member_briers) / len(member_briers) + 1e-9
    assert ens_brier <= max(member_briers)


def test_ensemble_modes_and_weights():
    s, y = _miscalibrated()
    med = CalibratorEnsemble(mode="median").fit(s, y)
    vals = med.calibrate_batch([0.1, 0.5, 0.9])
    assert all(0.0 <= v <= 1.0 for v in vals)
    weighted = CalibratorEnsemble(
        [(PlattCalibrator, 3.0), (TemperatureCalibrator, 1.0)]).fit(s, y)
    v = weighted.calibrate(0.7)
    manual = (0.75 * PlattCalibrator().fit(s, y).calibrate(0.7)
              + 0.25 * TemperatureCalibrator().fit(s, y).calibrate(0.7))
    assert v == pytest.approx(manual)
    assert weighted.member_spread(0.7) >= 0.0
    with pytest.raises(CalibrationError):
        CalibratorEnsemble(mode="geometric")
    with pytest.raises(CalibrationError):
        CalibratorEnsemble([(PlattCalibrator, -1.0)])
    with pytest.raises(CalibrationError):
        CalibratorEnsemble().calibrate(0.5)


def test_ensemble_params_round_trip():
    s, y = _miscalibrated()
    ens = CalibratorEnsemble(
        [(PlattCalibrator, 2.0), (IsotonicCalibrator, 1.0)]).fit(s, y)
    back = CalibratorEnsemble.from_params(ens.get_params())
    assert back.member_names == ["platt", "isotonic"]
    for v in (0.2, 0.5, 0.8):
        assert back.calibrate(v) == pytest.approx(ens.calibrate(v))
    assert CalibratorRegistry.get("ensemble") is CalibratorEnsemble
    # Rebuild through the registry's param path.
    rebuilt = CalibratorRegistry.build("ensemble", ens.get_params())
    assert rebuilt.calibrate(0.5) == pytest.approx(ens.calibrate(0.5))
