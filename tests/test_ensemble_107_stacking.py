"""Slice 107 — Stacking engine.

A softmax-regression meta-learner trained on member prediction
vectors. The centerpiece: it learns to trust the sharp member and
distrust the confidently-wrong one — something no fixed-weight vote
can do.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import ConstantBackend

from hugrgate import DecisionSpec
from hugrgate.ensemble import (
    Ensemble,
    SoftmaxRegression,
    StackingEngine,
    stacking_combine,
)
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError, PolicyError

BIN = DecisionSpec(type="binary", statement="s")
TWO = DecisionSpec(type="categorical", options=["yes", "no"])


def _vote(name, value, pt):
    dist = {"true": pt, "false": 1 - pt} if value == "true" else \
        {"true": 1 - pt, "false": pt}
    return MemberVote(backend=name, value=value, probability=pt,
                      distribution=dist)


def _sharp_dull_data(n=8):
    """sharp always right @0.9; dull always (confidently) wrong @0.9."""
    samples, labels = [], []
    for i in range(n):
        truth = "true" if i % 2 == 0 else "false"
        wrong = "false" if truth == "true" else "true"
        samples.append([_vote("sharp", truth, 0.9),
                        _vote("dull", wrong, 0.9)])
        labels.append(truth)
    return samples, labels


def _fitted_engine():
    samples, labels = _sharp_dull_data()
    return StackingEngine(["sharp", "dull"]).fit(samples, labels, BIN)


# --- success -----------------------------------------------------------------

def test_meta_learner_distrusts_the_confidently_wrong_member():
    engine = _fitted_engine()
    assert engine.fitted
    proba = engine.predict_proba(
        [_vote("sharp", "true", 0.9), _vote("dull", "false", 0.9)], BIN)
    assert proba["true"] > 0.9
    assert abs(sum(proba.values()) - 1.0) < 1e-9
    # and the mirror image
    proba = engine.predict_proba(
        [_vote("sharp", "false", 0.9), _vote("dull", "true", 0.9)], BIN)
    assert proba["false"] > 0.9


def test_fit_is_deterministic():
    samples, labels = _sharp_dull_data()
    e1 = StackingEngine(["sharp", "dull"]).fit(samples, labels, BIN)
    e2 = StackingEngine(["sharp", "dull"]).fit(samples, labels, BIN)
    assert e1.regression.weights == e2.regression.weights
    assert e1.regression.bias == e2.regression.bias


def test_stacking_combine_end_to_end():
    engine = _fitted_engine()
    members = [ConstantBackend("sharp", "true",
                               {"true": 0.9, "false": 0.1}),
               ConstantBackend("dull", "false",
                               {"true": 0.1, "false": 0.9})]
    ens = Ensemble(members, strategy="stacking").attach(engine)
    result = ens.evaluate({"x": 1}, BIN)
    assert result.value == "true"
    assert result.probability > 0.9
    meta = result.metadata["ensemble"]
    assert meta["strategy"] == "stacking"
    assert meta["meta_classes"] == ["true", "false"]


def test_softmax_regression_learns_a_toy_problem():
    reg = SoftmaxRegression(2, 2, iters=500)
    X = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]]
    reg.fit(X, [0, 0, 1, 1])
    assert reg.predict([1.0, 0.0]) == 0
    assert reg.predict([0.0, 1.0]) == 1
    assert reg.predict_proba([1.0, 0.0])[0] > 0.9


def test_to_dict():
    engine = _fitted_engine()
    d = engine.to_dict()
    assert d["members"] == ["sharp", "dull"]
    assert d["classes"] == ["true", "false"]
    assert d["fitted"] is True


# --- failure -----------------------------------------------------------------

def test_combine_needs_fitted_engine():
    votes = [_vote("sharp", "true", 0.9)]
    ctx = StrategyContext(spec=BIN, fitted=None)
    with pytest.raises(BackendError, match="fitted StackingEngine"):
        stacking_combine(votes, ctx)
    with pytest.raises(BackendError, match="fitted StackingEngine"):
        stacking_combine(votes, StrategyContext(
            spec=BIN, fitted=StackingEngine(["sharp"])))


def test_predict_before_fit():
    engine = StackingEngine(["sharp"])
    with pytest.raises(BackendError, match="before fit"):
        engine.predict_proba([_vote("sharp", "true", 0.9)], BIN)
    with pytest.raises(BackendError, match="before fit"):
        SoftmaxRegression(2, 2).predict_proba([1.0, 0.0])


def test_fit_validation():
    samples, labels = _sharp_dull_data()
    with pytest.raises(PolicyError, match="labels"):
        StackingEngine(["sharp", "dull"]).fit(samples, labels[:-1], BIN)
    with pytest.raises(PolicyError, match="outside the spec space"):
        StackingEngine(["sharp", "dull"]).fit(samples,
                                              ["maybe"] * len(labels),
                                              BIN)
    with pytest.raises(PolicyError, match="labeled samples"):
        StackingEngine(["sharp"]).fit([], [], BIN)
    with pytest.raises(PolicyError, match="unique"):
        StackingEngine(["a", "a"])
    with pytest.raises(PolicyError, match="at least one member"):
        StackingEngine([])
    with pytest.raises(BackendError, match="discrete spec"):
        numeric = DecisionSpec(type="numeric", minimum=0.0,
                               maximum=1.0)
        StackingEngine(["a"]).fit([], ["x"], numeric)


def test_regression_hyperparameter_validation():
    with pytest.raises(PolicyError, match="features"):
        SoftmaxRegression(0, 2)
    with pytest.raises(PolicyError, match="classes"):
        SoftmaxRegression(2, 1)
    with pytest.raises(PolicyError, match="l2"):
        SoftmaxRegression(2, 2, l2=-0.1)
    with pytest.raises(PolicyError, match="lr"):
        SoftmaxRegression(2, 2, lr=0.0)
    with pytest.raises(PolicyError, match="iters"):
        SoftmaxRegression(2, 2, iters=0)


def test_numeric_spec_rejected_by_combine():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(BackendError, match="discrete spec"):
        stacking_combine([], StrategyContext(spec=numeric,
                                             fitted=_fitted_engine()))


# --- boundary ----------------------------------------------------------------

def test_missing_member_votes_become_zero_features():
    engine = _fitted_engine()
    # dull silent: its feature block is zeros; sharp still decides
    proba = engine.predict_proba([_vote("sharp", "true", 0.9)], BIN)
    assert proba["true"] > 0.5


def test_spec_space_mismatch_rejected():
    engine = _fitted_engine()
    with pytest.raises(BackendError, match="differs from the fitted"):
        engine.predict_proba([_vote("sharp", "true", 0.9)], TWO)
