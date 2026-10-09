"""Slice 105 — Confidence-weighted voting.

Ballots weighted by each member's own reported confidence. Includes
the statistical validation: on controlled data where confidence is
rank-calibrated, the confident minority recovers the truth that hard
voting misses.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.ensemble import Ensemble, confidence_weighted_voting
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError
from ensemble_fakes import CAT_SPEC, ConstantBackend

TWO = DecisionSpec(type="categorical", options=["alpha", "beta"])
BIN = DecisionSpec(type="binary", statement="s")


def _ctx(spec=None):
    return StrategyContext(spec=spec or TWO)


def _voter(name, value, confidence):
    dist = {"alpha": 1.0 - confidence, "beta": confidence} \
        if value == "beta" else \
        {"alpha": confidence, "beta": 1.0 - confidence}
    return ConstantBackend(name, value, dist)


# --- success -----------------------------------------------------------------

def test_confident_minority_overrules_unsure_majority():
    # Controlled data: truth is "beta". Three members vote "alpha"
    # (wrong) at 0.55 confidence; two vote "beta" (right) at 0.95.
    # Hard voting follows the unsure majority; confidence weighting
    # follows the calibrated confidence — if and only if confidence
    # is rank-calibrated (confident members are the correct ones).
    members = [_voter("w1", "alpha", 0.55),
               _voter("w2", "alpha", 0.55),
               _voter("w3", "alpha", 0.55),
               _voter("c1", "beta", 0.95),
               _voter("c2", "beta", 0.95)]
    hard = Ensemble(members, strategy="hard").evaluate({"x": 1}, TWO)
    assert hard.value == "alpha"  # the unsure majority wins

    result = Ensemble(members, strategy="confidence").evaluate({"x": 1},
                                                               TWO)
    # scores: alpha = 3*0.55 = 1.65, beta = 2*0.95 = 1.90
    assert result.value == "beta"
    assert result.probability == pytest.approx(1.90 / 3.55)
    assert result.distribution == pytest.approx({"alpha": 1.65 / 3.55,
                                                 "beta": 1.90 / 3.55})
    meta = result.metadata["ensemble"]
    assert meta["confidence_scores"] == pytest.approx({"alpha": 1.65,
                                                       "beta": 1.90})
    assert meta["effective_weights"]["c1"] == pytest.approx(0.95)


def test_exact_score_math():
    members = [_voter("a", "alpha", 0.8), _voter("b", "beta", 0.6)]
    result = Ensemble(members, strategy="confidence").evaluate({"x": 1},
                                                               TWO)
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.8 / 1.4)
    assert result.uncertainty == pytest.approx(1 - 0.8 / 1.4)


def test_base_weights_multiply_confidence():
    members = [_voter("a", "alpha", 0.9), _voter("b", "beta", 0.9)]
    result = Ensemble(members, strategy="confidence",
                      weights={"a": 1.0, "b": 3.0}).evaluate({"x": 1},
                                                             TWO)
    # effective: normalized base (0.25/0.75) times confidence 0.9
    assert result.value == "beta"
    assert result.probability == pytest.approx(2.7 / 3.6)
    meta = result.metadata["ensemble"]
    assert meta["effective_weights"] == pytest.approx({"a": 0.225,
                                                       "b": 0.675})


def test_equal_confidence_matches_hard_voting():
    members = [_voter("a", "alpha", 0.7), _voter("b", "alpha", 0.7),
               _voter("c", "beta", 0.7)]
    conf = Ensemble(members, strategy="confidence").evaluate({"x": 1},
                                                             TWO)
    hard = Ensemble(members, strategy="hard").evaluate({"x": 1}, TWO)
    assert conf.value == hard.value == "alpha"
    assert conf.probability == pytest.approx(hard.probability)


def test_zero_confidence_member_contributes_nothing():
    def flat(state, spec):
        from hugrgate import DecisionResult
        return DecisionResult(value="alpha", probability=0.0,
                              distribution={"alpha": 0.5, "beta": 0.5},
                              backend="flat", model="fake")
    from ensemble_fakes import FnBackend
    members = [FnBackend("flat", flat), _voter("b", "beta", 0.8)]
    result = Ensemble(members, strategy="confidence").evaluate({"x": 1},
                                                               TWO)
    assert result.value == "beta"
    assert result.probability == pytest.approx(1.0)


# --- failure -----------------------------------------------------------------

def test_all_zero_confidence_raises():
    votes = [MemberVote(backend="a", value="alpha", probability=0.0,
                        distribution={"alpha": 0.5, "beta": 0.5},
                        weight=1.0)]
    with pytest.raises(BackendError, match="total confidence weight"):
        confidence_weighted_voting(votes, _ctx())


def test_no_ballots_raises():
    with pytest.raises(BackendError, match="no countable ballots"):
        confidence_weighted_voting([], _ctx())


def test_numeric_spec_rejected():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(BackendError, match="discrete spec"):
        confidence_weighted_voting([], _ctx(numeric))


# --- boundary ----------------------------------------------------------------

def test_binary_spec_end_to_end():
    members = [
        ConstantBackend("t", "true", {"true": 0.95, "false": 0.05}),
        ConstantBackend("f", "false", {"true": 0.45, "false": 0.55}),
    ]
    result = Ensemble(members, strategy="confidence").evaluate({"x": 1},
                                                               BIN)
    assert result.value == "true"
    assert result.probability == pytest.approx(0.95 / 1.50)
