"""Tests for slice 094 — uncertainty decomposition."""

from __future__ import annotations

import math

import pytest

from hugrgate.calibration.decomposition import (
    UncertaintyBreakdown,
    decompose,
    decompose_dicts,
)
from hugrgate.errors import CalibrationError


def test_identical_members_have_no_epistemic():
    b = decompose([[0.7, 0.2, 0.1]] * 5)
    assert isinstance(b, UncertaintyBreakdown)
    assert b.epistemic == pytest.approx(0.0, abs=1e-12)
    assert b.total == pytest.approx(b.aleatoric)
    assert b.n_members == 5 and b.n_classes == 3
    d = b.as_dict()
    assert set(d) == {"total", "aleatoric", "epistemic", "n_members",
                      "n_classes"}


def test_disagreement_is_epistemic():
    # Members confidently disagree: high epistemic, low aleatoric.
    preds = [[0.9, 0.05, 0.05], [0.05, 0.9, 0.05], [0.05, 0.05, 0.9]]
    b = decompose(preds)
    assert b.epistemic > b.aleatoric
    assert b.total == pytest.approx(b.aleatoric + b.epistemic)
    # Uniform members: maximal total, zero epistemic.
    u = decompose([[1 / 3] * 3] * 4)
    assert u.total == pytest.approx(math.log(3))
    assert u.epistemic == pytest.approx(0.0, abs=1e-12)


def test_decompose_dicts():
    preds = [{"a": 0.8, "b": 0.2}, {"a": 0.6, "b": 0.4}]
    b = decompose_dicts(preds)
    assert b.n_classes == 2 and b.n_members == 2
    assert b.epistemic > 0
    # Missing keys default to 0.
    b2 = decompose_dicts([{"a": 1.0}, {"b": 1.0}])
    assert b2.epistemic == pytest.approx(math.log(2), rel=1e-6)


def test_decompose_errors():
    with pytest.raises(CalibrationError):
        decompose([])
    with pytest.raises(CalibrationError):
        decompose([[0.5, 0.5], [0.3, 0.3]])  # rows must sum to 1
    with pytest.raises(CalibrationError):
        decompose([[-0.1, 1.1]])
    with pytest.raises(CalibrationError):
        decompose([[float("nan"), 1.0]])
    with pytest.raises(CalibrationError):
        decompose_dicts([])
    with pytest.raises(CalibrationError):
        decompose_dicts([{}])
