"""Tests for slice 092 — calibration auto-selection."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.autoselect import (
    DEFAULT_CANDIDATES,
    SelectionResult,
    auto_select,
)
from hugrgate.calibration.metrics import brier_score
from hugrgate.errors import CalibrationError


def _miscalibrated(n: int = 600, seed: int = 7):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.2, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    scores = 1.0 / (1.0 + np.exp(-2.0 * z))
    labels = (rng.random(n) < p_true).astype(int).tolist()
    return scores.tolist(), labels


def test_auto_select_picks_winner():
    s, y = _miscalibrated()
    res = auto_select(s, y, seed=0)
    assert isinstance(res, SelectionResult)
    assert set(DEFAULT_CANDIDATES) == {"platt", "isotonic", "temperature",
                                       "beta-binomial"}
    assert res.best in DEFAULT_CANDIDATES
    means = [r["mean"] for r in res.ranking]
    assert means == sorted(means)
    assert res.n_samples == 600
    # The winner beats doing nothing (raw scores) on held-out folds.
    raw_cv = []
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(s))
    for fold in [idx[i::5] for i in range(5)]:
        raw_cv.append(brier_score([y[i] for i in fold],
                                  [s[i] for i in fold]))
    assert res.ranking[0]["mean"] < float(np.mean(raw_cv))
    d = res.as_dict()
    assert d["best"] == res.best and "ranking" in d


def test_auto_select_deterministic():
    s, y = _miscalibrated()
    r1 = auto_select(s, y, seed=42)
    r2 = auto_select(s, y, seed=42)
    assert r1.best == r2.best
    assert r1.ranking == r2.ranking


def test_auto_select_metrics_and_candidates():
    s, y = _miscalibrated()
    for metric in ("brier", "log_loss", "ece"):
        res = auto_select(s, y, metric=metric,
                          candidates=["platt", "temperature"], seed=1)
        assert res.metric == metric
        assert {r["name"] for r in res.ranking} == {"platt", "temperature"}
    with pytest.raises(CalibrationError):
        auto_select(s, y, metric="r2")
    with pytest.raises(CalibrationError):
        auto_select(s, y, candidates=["nope"])
    with pytest.raises(CalibrationError):
        auto_select(s, y, candidates=[])
    with pytest.raises(CalibrationError):
        auto_select(s, y, n_folds=1)
    with pytest.raises(CalibrationError):
        auto_select([], [])
