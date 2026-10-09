"""Slice 454 — threshold tuner. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Disposition,
    Mode,
    OptimizationController,
    TunableParameter,
)
from hugrgate.autotune.tuners._base import kfold_indices, linspace, seeded_rng
from hugrgate.autotune.tuners.thresholds import ThresholdTuner, threshold_metric
from hugrgate.errors import TunerError


def _dataset(seed: int = 11, n: int = 200):
    """Separable scores: negatives ~ U(0, 0.45), positives ~ U(0.55, 1)."""
    rng = seeded_rng(seed)
    out = []
    for _ in range(n // 2):
        out.append((rng.uniform(0.0, 0.45), 0))
    for _ in range(n // 2):
        out.append((rng.uniform(0.55, 1.0), 1))
    rng.shuffle(out)
    return out


def _ctx(store=None, seed=5):
    from hugrgate.autotune.controller import TuningContext
    s = store or ConfigStore()
    return TuningContext(store=s, objectives={}, constraints=[], seed=seed,
                         mode=Mode.OFFLINE, run_id="r")


def _store_with(threshold=0.9):
    s = ConfigStore()
    s.register(TunableParameter(name="min_prob", dtype="float",
                                default=threshold, lo=0.0, hi=1.0))
    return s


def test_metric_f1_perfect_separation():
    data = _dataset()
    scores = [s for s, _ in data]
    labels = [lab for _, lab in data]
    assert threshold_metric("f1", scores, labels, 0.5) == pytest.approx(1.0)
    assert threshold_metric("f1", scores, labels, 0.0) < 1.0


def test_metric_variants():
    data = _dataset()
    scores = [s for s, _ in data]
    labels = [lab for _, lab in data]
    assert threshold_metric("accuracy", scores, labels, 0.5) == pytest.approx(1.0)
    assert threshold_metric("youden", scores, labels, 0.5) == pytest.approx(1.0)
    assert threshold_metric("precision", scores, labels, 0.5) == pytest.approx(1.0)
    assert threshold_metric("recall", scores, labels, 0.5) == pytest.approx(1.0)
    f2 = threshold_metric("f_beta:2.0", scores, labels, 0.5)
    assert f2 == pytest.approx(1.0)


def test_unknown_metric_rejected():
    with pytest.raises(TunerError):
        threshold_metric("nope", [0.1], [0], 0.5)
    with pytest.raises(TunerError):
        threshold_metric("f_beta:xx", [0.1], [0], 0.5)


def test_tuner_finds_separating_threshold():
    t = ThresholdTuner(param="min_prob", objective_id="f1",
                       dataset=_dataset(), metric="f1", seed=1)
    prop = t.tune(_ctx(_store_with(threshold=0.9)))
    assert prop is not None
    assert 0.45 <= prop.changes["min_prob"] <= 0.55
    assert prop.delta > 0
    assert prop.evidence["n_folds"] == 5
    assert len(prop.evidence["per_fold_best"]) == 5


def test_tuner_silent_when_already_optimal():
    t = ThresholdTuner(param="min_prob", objective_id="f1",
                       dataset=_dataset(), metric="f1", seed=1,
                       min_delta=0.5)
    prop = t.tune(_ctx(_store_with(threshold=0.5)))
    assert prop is None  # already at the optimum; no noise proposal


def test_tuner_noisy_data_stays_conservative():
    rng = seeded_rng(3)
    data = [(rng.random(), rng.choice([0, 1])) for _ in range(300)]
    t = ThresholdTuner(param="min_prob", objective_id="acc",
                       dataset=data, metric="accuracy", seed=1,
                       min_delta=0.02)
    prop = t.tune(_ctx(_store_with(threshold=0.5)))
    # pure noise: held-out accuracy ~0.5 everywhere; one-SE rule must
    # not propose a "win" beyond min_delta
    assert prop is None


def test_tuner_rejects_non_float_param():
    s = ConfigStore()
    s.register(TunableParameter(name="n", dtype="int", default=1,
                                lo=1, hi=5))
    t = ThresholdTuner(param="n", objective_id="o", dataset=_dataset(),
                       seed=1)
    with pytest.raises(TunerError):
        t.tune(_ctx(s))


def test_tuner_validates_dataset():
    with pytest.raises(TunerError):
        ThresholdTuner(param="p", objective_id="o",
                       dataset=[(0.1, 0)] * 3, seed=1)  # too small
    with pytest.raises(TunerError):
        ThresholdTuner(param="p", objective_id="o",
                       dataset=[(0.1, 2)] * 20, seed=1)  # bad label
    with pytest.raises(TunerError):
        ThresholdTuner(param="", objective_id="o",
                       dataset=_dataset(), seed=1)


def test_kfold_stratified():
    labels = [0] * 50 + [1] * 50
    folds = kfold_indices(100, labels, 5, seed=9)
    assert len(folds) == 5
    for train, test in folds:
        assert len(test) == 20
        assert sum(labels[i] for i in test) == 10  # stratified
        assert len(train) == 80


def test_linspace():
    assert linspace(0.0, 1.0, 1) == [0.0]
    assert linspace(0.0, 1.0, 3) == [0.0, 0.5, 1.0]
    with pytest.raises(TunerError):
        linspace(0.0, 1.0, 0)


def test_end_to_end_through_controller():
    store = _store_with(threshold=0.9)
    c = OptimizationController(store=store)
    c.register_objective("f1", lambda values: 0.0)
    c.register_tuner(ThresholdTuner(param="min_prob", objective_id="f1",
                                    dataset=_dataset(), seed=2))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].disposition == Disposition.RECORDED
    assert store.get("min_prob") == 0.9  # offline: untouched
