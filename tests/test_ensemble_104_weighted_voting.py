"""Slice 104 — Weighted voting.

Ballots counted with member weights: trusted members count more.
Distinct from hard voting (one member one ballot) and soft voting
(which averages whole distributions).
"""

from __future__ import annotations

import pytest
from ensemble_fakes import CAT_SPEC, ConstantBackend

from hugrgate import DecisionSpec
from hugrgate.ensemble import Ensemble, weighted_voting
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}
TWO = DecisionSpec(type="categorical", options=["alpha", "beta"])


def _ctx(spec=None):
    return StrategyContext(spec=spec or TWO)


# --- success -----------------------------------------------------------------

def test_weighted_scores_elect_winner():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        ConstantBackend("b", "beta", {"alpha": 0.2, "beta": 0.8}),
        ConstantBackend("c", "alpha", {"alpha": 0.8, "beta": 0.2}),
    ]
    # alpha: 1+1=2, beta: 3 -> beta wins despite 1-2 ballot minority
    result = Ensemble(members, strategy="weighted",
                      weights={"a": 1.0, "b": 3.0,
                               "c": 1.0}).evaluate({"x": 1}, TWO)
    assert result.value == "beta"
    assert result.probability == pytest.approx(0.6)
    assert result.distribution == pytest.approx({"alpha": 0.4,
                                                 "beta": 0.6})
    assert result.uncertainty == pytest.approx(0.4)
    meta = result.metadata["ensemble"]
    assert meta["strategy"] == "weighted"
    assert meta["weighted_tally"] == pytest.approx({"alpha": 0.4,
                                                    "beta": 0.6})
    assert meta["winner_share"] == pytest.approx(0.6)
    assert [r["backend"] for r in meta["minority_report"]] == ["a", "c"]


def test_equal_weights_match_hard_voting():
    members = [
        ConstantBackend("a", "alpha", ALPHA),
        ConstantBackend("b", "alpha", ALPHA),
        ConstantBackend("c", "beta", BETA),
    ]
    weighted = Ensemble(members, strategy="weighted").evaluate(
        {"x": 1}, CAT_SPEC())
    hard = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                       CAT_SPEC())
    assert weighted.value == hard.value == "alpha"
    assert weighted.probability == pytest.approx(hard.probability)


def test_weighted_tie_breaks_deterministically():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        ConstantBackend("b", "beta", {"alpha": 0.2, "beta": 0.8}),
    ]
    winners = {Ensemble(members, strategy="weighted",
                        weights={"a": 1.0, "b": 1.0}).evaluate(
                            {"x": 1}, TWO).value for _ in range(3)}
    assert winners == {"alpha"}  # earliest ballot wins the tie


def test_unnamed_member_gets_zero_weight():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        ConstantBackend("b", "beta", {"alpha": 0.2, "beta": 0.8}),
    ]
    result = Ensemble(members, strategy="weighted",
                      weights={"a": 1.0}).evaluate({"x": 1}, TWO)
    assert result.value == "alpha"
    assert result.probability == pytest.approx(1.0)


# --- failure -----------------------------------------------------------------

def test_no_ballots_raises():
    with pytest.raises(BackendError, match="no countable ballots"):
        weighted_voting([], _ctx())


def test_zero_total_weight_raises():
    votes = [MemberVote(backend="a", value="alpha", probability=0.8,
                        distribution={"alpha": 0.8, "beta": 0.2},
                        weight=0.0)]
    with pytest.raises(BackendError, match="total member weight"):
        weighted_voting(votes, _ctx())


def test_numeric_spec_rejected():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(BackendError, match="discrete spec"):
        weighted_voting([], _ctx(numeric))


# --- boundary ----------------------------------------------------------------

def test_single_member_full_share():
    result = Ensemble([ConstantBackend("solo", "beta", BETA)],
                      strategy="weighted",
                      weights={"solo": 5.0}).evaluate({"x": 1}, CAT_SPEC())
    assert result.value == "beta"
    assert result.probability == pytest.approx(1.0)
    assert result.uncertainty == pytest.approx(0.0)


def test_fractional_weights():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        ConstantBackend("b", "beta", {"alpha": 0.2, "beta": 0.8}),
    ]
    result = Ensemble(members, strategy="weighted",
                      weights={"a": 0.25, "b": 0.75}).evaluate(
                          {"x": 1}, TWO)
    assert result.value == "beta"
    assert result.probability == pytest.approx(0.75)
