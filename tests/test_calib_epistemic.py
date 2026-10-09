"""Tests for slice 095 — epistemic uncertainty adapters."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.epistemic import (
    EpistemicReport,
    combine_epistemic,
    distance_epistemic,
    ensemble_epistemic,
    ensemble_epistemic_dicts,
    review_on_epistemic,
)
from hugrgate.errors import CalibrationError
from hugrgate.result import DecisionResult


def _result() -> DecisionResult:
    return DecisionResult(
        value="a", probability=0.8, distribution={"a": 0.8, "b": 0.2},
        uncertainty=0.2, accepted=True, backend="rules", model="m",
        metadata={})


def test_ensemble_epistemic_wrappers():
    b = ensemble_epistemic([[0.9, 0.1], [0.1, 0.9]])
    assert b.epistemic > 0.3
    b2 = ensemble_epistemic_dicts([{"a": 0.9, "b": 0.1},
                                   {"a": 0.1, "b": 0.9}])
    assert b2.epistemic == pytest.approx(b.epistemic)


def test_distance_epistemic():
    cloud = np.linspace(0.2, 0.8, 50).tolist()
    assert distance_epistemic(0.5, cloud) == 0.0
    assert distance_epistemic(0.2, cloud) == 0.0
    assert distance_epistemic(0.8, cloud) == 0.0
    d = distance_epistemic(1.4, cloud)
    assert d == pytest.approx(0.6 / 0.6)  # (1.4-0.8)/0.6 → clipped to 1
    assert distance_epistemic(0.9, cloud) == pytest.approx(0.1 / 0.6)
    assert distance_epistemic(100.0, cloud) == 1.0
    with pytest.raises(CalibrationError):
        distance_epistemic(float("nan"), cloud)
    with pytest.raises(CalibrationError):
        distance_epistemic(0.5, [])


def test_combine_epistemic():
    assert combine_epistemic([0.1, 0.7, 0.3]) == pytest.approx(0.7)
    with pytest.raises(CalibrationError):
        combine_epistemic([])
    with pytest.raises(CalibrationError):
        combine_epistemic([-0.1])


def test_review_gate():
    res = _result()
    out, report = review_on_epistemic(res, 0.9, threshold=0.5)
    assert isinstance(report, EpistemicReport)
    assert report.triggered is True
    assert out.accepted is False
    assert out.metadata["policy_verdict"] == "review"
    assert out.metadata["reviewer"] == "calibration-epistemic-gate"
    assert res.accepted is True  # original untouched
    out2, report2 = review_on_epistemic(res, 0.1, threshold=0.5)
    assert report2.triggered is False
    assert out2 is res
    d = report.as_dict()
    assert d["adapter"] == "review-gate" and d["value"] == 0.9
    with pytest.raises(CalibrationError):
        review_on_epistemic(res, 0.9, threshold=-1.0)
