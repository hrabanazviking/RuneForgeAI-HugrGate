"""Tests for slice 082 — conformal classification."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.calibration.conformal import ConformalClassifier
from hugrgate.errors import CalibrationError


def _data(n: int, seed: int, n_classes: int = 4):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, (n, n_classes))
    p = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
    labels_idx = (rng.random(n)[:, None] < p.cumsum(axis=1)).argmax(axis=1)
    names = [f"c{i}" for i in range(n_classes)]
    probas = [dict(zip(names, row)) for row in p]
    labels = [names[i] for i in labels_idx]
    return probas, labels


def test_conformal_coverage_guarantee():
    # Well-specified probs: empirical coverage should sit at/above 1−α.
    cal_probas, cal_labels = _data(1500, 1)
    test_probas, test_labels = _data(3000, 2)
    cc = ConformalClassifier(alpha=0.1).fit(cal_probas, cal_labels)
    cov = cc.empirical_coverage(test_probas, test_labels)
    assert 0.88 <= cov <= 1.0  # guarantee is ≥ 0.9; tolerance for noise
    assert cov >= 0.9 - 0.02
    assert cc.mean_set_size(test_probas) >= 1.0


def test_conformal_alpha_trades_size_for_coverage():
    cal_probas, cal_labels = _data(1500, 3)
    test_probas, test_labels = _data(1500, 4)
    small = ConformalClassifier(alpha=0.3).fit(cal_probas, cal_labels)
    big = ConformalClassifier(alpha=0.05).fit(cal_probas, cal_labels)
    assert (small.mean_set_size(test_probas)
            <= big.mean_set_size(test_probas))
    assert (small.empirical_coverage(test_probas, test_labels)
            <= big.empirical_coverage(test_probas, test_labels) + 0.05)


def test_conformal_mondrian_groups():
    cal_probas, cal_labels = _data(1200, 5)
    test_probas, test_labels = _data(2000, 6)
    rng = np.random.default_rng(7)
    cal_g = rng.choice(["g1", "g2"], 1200).tolist()
    test_g = rng.choice(["g1", "g2"], 2000).tolist()
    cc = ConformalClassifier(alpha=0.1).fit(cal_probas, cal_labels,
                                            groups=cal_g)
    assert set(cc.thresholds) == {"g1", "g2"}
    for g in ("g1", "g2"):
        idx = [i for i, gg in enumerate(test_g) if gg == g]
        cov = cc.empirical_coverage([test_probas[i] for i in idx],
                                    [test_labels[i] for i in idx],
                                    [test_g[i] for i in idx])
        assert cov >= 0.9 - 0.05, (g, cov)
    with pytest.raises(CalibrationError):
        cc.predict_set(test_probas[0], group="unknown-group")


def test_conformal_errors():
    cc = ConformalClassifier()
    with pytest.raises(CalibrationError):
        cc.predict_set({"a": 1.0})
    with pytest.raises(CalibrationError):
        cc.fit([], [])
    with pytest.raises(CalibrationError):
        ConformalClassifier(alpha=0.0)
    with pytest.raises(CalibrationError):
        ConformalClassifier(alpha=1.0)
    p, lab = _data(10, 8)
    with pytest.raises(CalibrationError):
        cc.fit(p, lab[:5])
