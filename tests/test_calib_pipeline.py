"""Tests for slice 076 — calibration pipeline (architecture v2)."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    TemperatureCalibrator,
)
from hugrgate.calibration.pipeline import (
    MIN_FIT_SAMPLES,
    CalibrationPipeline,
    CalibrationReport,
    validate_fit_data,
)
from hugrgate.errors import CalibrationError


def _miscalibrated(n: int = 400, seed: int = 7):
    """Overconfident scores: true p = sigmoid(z), reported = sigmoid(2z)."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.2, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-2.0 * z))
    labels = (rng.random(n) < p_true).astype(int)
    return scores.tolist(), labels.tolist()


def test_validate_fit_data_ok():
    s, y = _miscalibrated()
    d = validate_fit_data(s, y)
    assert d.n_samples == 400
    assert d.n_positive + d.n_negative == 400
    assert 0.0 <= d.score_min <= d.score_max <= 1.0
    assert len(d.dataset_hash) == 64


def test_validate_fit_data_failures():
    s, y = _miscalibrated()
    with pytest.raises(CalibrationError):
        validate_fit_data([], [])
    with pytest.raises(CalibrationError):
        validate_fit_data(s, y[:10])
    with pytest.raises(CalibrationError):
        validate_fit_data(s[: MIN_FIT_SAMPLES - 1], y[: MIN_FIT_SAMPLES - 1])
    with pytest.raises(CalibrationError):
        validate_fit_data([0.5] * 20, [1] * 20)  # single class
    with pytest.raises(CalibrationError):
        bad = list(s)
        bad[3] = float("nan")
        validate_fit_data(bad, y)
    with pytest.raises(CalibrationError):
        validate_fit_data([0.5] * 20, [2] * 20)  # bad labels


@pytest.mark.parametrize("factory", [PlattCalibrator, IsotonicCalibrator,
                                     TemperatureCalibrator])
def test_pipeline_improves_miscalibrated(factory):
    s, y = _miscalibrated()
    pipe = CalibrationPipeline(factory)
    report = pipe.fit(s, y, provenance={"slice": "076"})
    assert report.improved
    assert report.improvement("brier") > 0
    assert report.improvement("ece") > 0
    assert report.provenance == {"slice": "076"}
    out = pipe.apply([0.1, 0.5, 0.9])
    assert len(out) == 3 and all(0.0 <= v <= 1.0 for v in out)


def test_pipeline_fit_strict_raises_when_no_gain():
    # A no-op calibrator provably cannot improve anything, so strict mode
    # must refuse to bless the fit.  (A real 1-parameter fit on finite data
    # can still eke out in-sample Brier gain via optimism, so this uses a
    # deterministic identity map instead of optimizer behavior.)
    from hugrgate.calibration._base import Calibrator

    class IdentityCalibrator(Calibrator):
        name = "identity"

        def fit(self, scores, labels):
            self._check_arrays(scores, labels)
            self._fitted = True
            return self

        def _check_arrays(self, scores, labels):
            self._as_arrays(scores, labels)

        def calibrate(self, score):
            self._check_fitted()
            return float(score)

        def get_params(self):
            return {}

        @classmethod
        def from_params(cls, params):
            obj = cls()
            obj._fitted = True
            return obj

    s, y = _miscalibrated()
    pipe = CalibrationPipeline(IdentityCalibrator)
    report = pipe.fit(s, y)
    assert not report.improved
    with pytest.raises(CalibrationError):
        pipe.fit_strict(s, y)


def test_pipeline_apply_before_fit_raises():
    pipe = CalibrationPipeline(PlattCalibrator)
    with pytest.raises(CalibrationError):
        pipe.apply([0.5])
    with pytest.raises(CalibrationError):
        CalibrationPipeline(lambda: object())  # bad factory


def test_report_round_trip():
    s, y = _miscalibrated()
    report = CalibrationPipeline(IsotonicCalibrator).fit(s, y)
    d = report.as_dict()
    back = CalibrationReport.from_dict(d)
    assert back.calibrator_name == report.calibrator_name
    assert back.metrics_after == report.metrics_after
    assert back.improved == report.improved
    assert back.diagnostics["dataset_hash"] == report.diagnostics["dataset_hash"]
