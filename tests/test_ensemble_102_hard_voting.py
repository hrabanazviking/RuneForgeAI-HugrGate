"""Slice 102 — Hard voting.

One member, one ballot; the majority value wins. Covers the vote-share
math, the deterministic tie-break ladder, and the abstention-shaped
result hardening in collect_votes.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionSpec
from hugrgate.ensemble import Ensemble, hard_voting
from hugrgate.ensemble.base import StrategyContext, collect_votes
from hugrgate.errors import BackendError
from ensemble_fakes import (
    CAT_SPEC,
    AbstainingBackend,
    ConstantBackend,
    FailingBackend,
    FnBackend,
    make_result,
)

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}
GAMMA = {"alpha": 0.1, "beta": 0.3, "gamma": 0.6}


def _ctx(spec=None):
    return StrategyContext(spec=spec or CAT_SPEC())


# --- success -----------------------------------------------------------------

def test_majority_wins_with_vote_share():
    members = [
        ConstantBackend("a", "alpha", ALPHA),
        ConstantBackend("b", "alpha", ALPHA),
        ConstantBackend("c", "gamma", GAMMA),
    ]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert result.value == "alpha"
    assert result.probability == pytest.approx(2 / 3)
    assert result.distribution["alpha"] == pytest.approx(2 / 3)
    assert result.distribution["gamma"] == pytest.approx(1 / 3)
    assert result.distribution["beta"] == pytest.approx(0.0)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-9
    assert result.uncertainty == pytest.approx(1 / 3)
    meta = result.metadata["ensemble"]
    assert meta["strategy"] == "hard"
    assert meta["tally"] == {"alpha": 2, "gamma": 1}
    assert meta["winner_share"] == pytest.approx(2 / 3)
    assert [r["backend"] for r in meta["minority_report"]] == ["c"]


def test_unanimous_vote_has_zero_uncertainty():
    members = [ConstantBackend("a", "beta", BETA),
               ConstantBackend("b", "beta", BETA)]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert result.value == "beta"
    assert result.probability == pytest.approx(1.0)
    assert result.uncertainty == pytest.approx(0.0)
    assert result.metadata["ensemble"]["minority_report"] == []


def test_tie_broken_by_confidence():
    # 1-1 tie: the more self-confident camp wins.
    members = [
        ConstantBackend("cool", "alpha", {"alpha": 0.55, "beta": 0.45}),
        ConstantBackend("sure", "beta", {"alpha": 0.05, "beta": 0.95}),
    ]
    spec = DecisionSpec(type="categorical", options=["alpha", "beta"])
    result = Ensemble(members, strategy="hard").evaluate({"x": 1}, spec)
    assert result.value == "beta"
    assert result.metadata["ensemble"]["tie_broken_by"] == "confidence"


def test_tie_broken_by_earliest_ballot():
    # 1-1 tie with equal confidence: earliest ballot wins.
    members = [
        ConstantBackend("first", "alpha", {"alpha": 0.6, "beta": 0.4}),
        ConstantBackend("second", "beta", {"alpha": 0.4, "beta": 0.6}),
    ]
    spec = DecisionSpec(type="categorical", options=["alpha", "beta"])
    winners = {Ensemble(members, strategy="hard").evaluate({"x": 1}, spec).value
               for _ in range(3)}
    assert winners == {"alpha"}


def test_weights_do_not_buy_extra_ballots():
    # Hard voting is one member one ballot, even with weights set:
    # a 1-1 tie goes to the earliest ballot, not the heavier weight.
    spec = DecisionSpec(type="categorical", options=["alpha", "beta"])
    members = [ConstantBackend("a", "alpha", {"alpha": 0.6, "beta": 0.4}),
               ConstantBackend("b", "beta", {"alpha": 0.4, "beta": 0.6})]
    result = Ensemble(members, strategy="hard",
                      weights={"a": 100.0, "b": 1.0}).evaluate({"x": 1},
                                                               spec)
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.5)


def test_binary_and_ordinal_specs():
    bspec = DecisionSpec(type="binary", statement="s")
    members = [
        FnBackend("t1", lambda s, spec: make_result(
            "true", {"true": 0.9, "false": 0.1}, "t1")),
        FnBackend("t2", lambda s, spec: make_result(
            "true", {"true": 0.8, "false": 0.2}, "t2")),
        FnBackend("f1", lambda s, spec: make_result(
            "false", {"true": 0.3, "false": 0.7}, "f1")),
    ]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1}, bspec)
    assert result.value == "true"
    assert result.probability == pytest.approx(2 / 3)

    ospec = DecisionSpec(type="ordinal", levels=["low", "mid", "high"])
    omembers = [
        FnBackend("o1", lambda s, spec: make_result(
            "high", {"low": 0.1, "mid": 0.2, "high": 0.7}, "o1")),
        FnBackend("o2", lambda s, spec: make_result(
            "high", {"low": 0.2, "mid": 0.2, "high": 0.6}, "o2")),
    ]
    result = Ensemble(omembers, strategy="hard").evaluate({"x": 1}, ospec)
    assert result.value == "high"


def test_single_member_elects_itself():
    result = Ensemble([ConstantBackend("solo", "gamma", GAMMA)],
                      strategy="hard").evaluate({"x": 1}, CAT_SPEC())
    assert result.value == "gamma"
    assert result.probability == pytest.approx(1.0)


def test_failing_members_do_not_vote():
    members = [
        ConstantBackend("a", "alpha", ALPHA),
        FailingBackend("bad"),
        AbstainingBackend("shy"),
        ConstantBackend("b", "alpha", ALPHA),
    ]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert result.value == "alpha"
    assert result.probability == pytest.approx(1.0)
    assert result.metadata["ensemble"]["usable_votes"] == 2


# --- failure -----------------------------------------------------------------

def test_no_ballots_raises():
    with pytest.raises(BackendError, match="no countable ballots"):
        hard_voting([], _ctx())


def test_numeric_spec_rejected():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(BackendError, match="discrete spec"):
        hard_voting([], _ctx(numeric))


def test_all_abstain_raises_backend_error():
    ens = Ensemble([AbstainingBackend("s1"), AbstainingBackend("s2")],
                   strategy="hard")
    with pytest.raises(BackendError, match="only 0 of 2 members"):
        ens.evaluate({"x": 1}, CAT_SPEC())


# --- boundary ----------------------------------------------------------------

def test_abstention_shaped_result_is_skipped():
    # A member returning value=None (instead of raising Abstention)
    # is recorded as skipped, not counted as a "None" ballot.
    def none_voter(state, spec):
        r = make_result("alpha", ALPHA, "none")
        r.value = None
        r.probability = 0.0
        r.distribution = {"alpha": 1 / 3, "beta": 1 / 3, "gamma": 1 / 3}
        r.accepted = False
        return r

    members = [ConstantBackend("a", "alpha", ALPHA),
               FnBackend("none", none_voter)]
    votes = collect_votes(members, {"x": 1}, CAT_SPEC())
    assert len(votes) == 2
    assert votes[1].skipped
    assert votes[1].skip_reason == "abstained_result"
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert result.value == "alpha"
    assert result.probability == pytest.approx(1.0)


def test_five_way_split_share_math():
    members = [
        ConstantBackend("a", "alpha", ALPHA),
        ConstantBackend("b", "beta", BETA),
        ConstantBackend("c", "gamma", GAMMA),
        ConstantBackend("d", "alpha", ALPHA),
        ConstantBackend("e", "beta", BETA),
    ]
    result = Ensemble(members, strategy="hard").evaluate({"x": 1},
                                                         CAT_SPEC())
    # alpha:2 beta:2 gamma:1 -> tie alpha/beta, alpha more confident
    # (0.7+0.7=1.4 vs 0.6+0.6=1.2)
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.4)
    assert result.distribution == pytest.approx(
        {"alpha": 0.4, "beta": 0.4, "gamma": 0.2})
