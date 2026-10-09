"""Tests for slice 084 — prediction sets."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.conformal import ConformalClassifier
from hugrgate.calibration.sets import (
    PredictionSet,
    cumulative_set,
    from_conformal,
    set_metrics,
    size_stratified_coverage,
    threshold_set,
    topk_set,
)
from hugrgate.errors import CalibrationError


def test_strategies():
    p = {"a": 0.6, "b": 0.3, "c": 0.1}
    assert threshold_set(p, 0.25).labels == frozenset({"a", "b"})
    assert topk_set(p, 2).labels == frozenset({"a", "b"})
    assert topk_set(p, 9).labels == frozenset({"a", "b", "c"})
    cs = cumulative_set(p, 0.89)
    assert cs.labels == frozenset({"a", "b"})
    assert cs.params["covered_mass"] == pytest.approx(0.6 + 0.3)
    # Empty-by-threshold falls back to argmax, never empty.
    assert threshold_set(p, 0.99).labels == frozenset({"a"})
    for bad in (lambda: threshold_set(p, 0.0), lambda: topk_set(p, 0),
                lambda: cumulative_set(p, 1.5), lambda: threshold_set({}, 0.5),
                lambda: PredictionSet(frozenset(), "x")):
        with pytest.raises(CalibrationError):
            bad()


def test_from_conformal_matches_raw():
    rng = np.random.default_rng(0)
    names = ["a", "b", "c"]
    probas = [dict(zip(names, rng.dirichlet([2, 2, 2]))) for _ in range(300)]
    labels = [names[int(rng.integers(0, 3))] for _ in range(300)]
    cc = ConformalClassifier(alpha=0.2).fit(probas, labels)
    ps = from_conformal(probas[0], cc)
    assert ps.method == "conformal"
    assert ps.labels == cc.predict_set(probas[0])
    assert ps.params["alpha"] == pytest.approx(0.2)


def test_set_metrics_and_stratification():
    rng = np.random.default_rng(3)
    names = ["a", "b", "c", "d"]
    probas, labels = [], []
    for _ in range(800):
        z = rng.normal(0, 1, 4)
        pr = np.exp(z) / np.exp(z).sum()
        probas.append(dict(zip(names, pr)))
        labels.append(names[int((rng.random() < np.cumsum(pr)).argmax())])
    sets = [cumulative_set(p, 0.9) for p in probas]
    m = set_metrics(sets, labels)
    assert 0.85 <= m["coverage"] <= 1.0
    assert m["mean_size"] >= 1.0
    assert m["n"] == 800
    rows = size_stratified_coverage(sets, labels)
    assert all(set(r) == {"size", "n", "coverage"} for r in rows)
    assert sum(r["n"] for r in rows) == 800
    # Well-specified probs: stratified coverage roughly flat.
    covs = [r["coverage"] for r in rows if r["n"] >= 30]
    assert max(covs) - min(covs) < 0.15
    with pytest.raises(CalibrationError):
        set_metrics(sets, labels[:10])
    with pytest.raises(CalibrationError):
        set_metrics([], [])


def test_prediction_set_immutable_audit():
    ps = topk_set({"a": 0.5, "b": 0.5}, 1)
    assert ps.covers("a") or ps.covers("b")
    assert ps.size == 1
    d = ps.as_dict()
    assert d["method"] == "top-k" and d["labels"] == sorted(ps.labels)
