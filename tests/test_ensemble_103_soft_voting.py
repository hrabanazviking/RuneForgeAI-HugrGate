"""Slice 103 — Soft voting hardening.

Weight-aware averaging and empty-distribution completion: an
incomplete ballot must never silently dilute the average.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import CAT_SPEC, ConstantBackend, FnBackend

from hugrgate import DecisionResult, DecisionSpec
from hugrgate.ensemble import Ensemble, soft_voting
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError

TWO = DecisionSpec(type="categorical", options=["alpha", "beta"])


def _ctx(spec=None):
    return StrategyContext(spec=spec or TWO)


def _empty_dist_member(name, value, probability):
    def fn(state, spec):
        return DecisionResult(value=value, probability=probability,
                              distribution={}, backend=name,
                              model="fake")
    return FnBackend(name, fn)


# --- success -----------------------------------------------------------------

def test_weights_shift_the_average():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        ConstantBackend("b", "beta", {"alpha": 0.2, "beta": 0.8}),
    ]
    result = Ensemble(members, strategy="soft",
                      weights={"a": 3.0, "b": 1.0}).evaluate({"x": 1}, TWO)
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.65)
    assert result.distribution == pytest.approx({"alpha": 0.65,
                                                 "beta": 0.35})
    meta = result.metadata["ensemble"]
    assert meta["weights"] == pytest.approx({"a": 0.75, "b": 0.25})


def test_unweighted_average_unchanged():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        ConstantBackend("b", "beta", {"alpha": 0.2, "beta": 0.8}),
    ]
    result = Ensemble(members, strategy="soft").evaluate({"x": 1}, TWO)
    assert result.distribution == pytest.approx({"alpha": 0.5,
                                                 "beta": 0.5})
    # exact tie -> earliest ballot wins, deterministically
    assert result.value == "alpha"


def test_empty_distribution_is_completed():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.8, "beta": 0.2}),
        _empty_dist_member("thin", "beta", 0.6),
    ]
    result = Ensemble(members, strategy="soft").evaluate({"x": 1}, TWO)
    # thin completes to {beta: 0.6, alpha: 0.4}; average:
    # alpha = (0.8 + 0.4)/2 = 0.6, beta = (0.2 + 0.6)/2 = 0.4
    assert result.distribution == pytest.approx({"alpha": 0.6,
                                                 "beta": 0.4})
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-9
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.6)
    completed = result.metadata["ensemble"]["completed_distributions"]
    assert completed == ["thin"]


def test_completion_with_certainty():
    members = [_empty_dist_member("sure", "alpha", 1.0)]
    result = Ensemble(members, strategy="soft").evaluate({"x": 1}, TWO)
    assert result.distribution == pytest.approx({"alpha": 1.0,
                                                 "beta": 0.0})
    assert result.value == "alpha"
    assert result.uncertainty == pytest.approx(0.0)


def test_completion_over_three_options():
    members = [_empty_dist_member("thin", "gamma", 0.7)]
    result = Ensemble(members, strategy="soft").evaluate({"x": 1},
                                                         CAT_SPEC())
    assert result.distribution == pytest.approx(
        {"alpha": 0.15, "beta": 0.15, "gamma": 0.7})
    assert result.value == "gamma"


def test_incomplete_ballot_no_longer_dilutes():
    # Old behavior: the empty-distribution member counted in the
    # divisor while contributing nothing (sums broke). New behavior:
    # its ballot is completed, so the average stays a distribution.
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.9, "beta": 0.1}),
        _empty_dist_member("thin", "alpha", 0.9),
    ]
    result = Ensemble(members, strategy="soft").evaluate({"x": 1}, TWO)
    assert abs(sum(result.distribution.values()) - 1.0) < 1e-9
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.9)


# --- failure -----------------------------------------------------------------

def test_zero_total_weight_rejected():
    votes = [MemberVote(backend="a", value="alpha", probability=0.8,
                        distribution={"alpha": 0.8, "beta": 0.2},
                        weight=0.0)]
    with pytest.raises(BackendError, match="total member weight"):
        soft_voting(votes, _ctx())


def test_no_usable_votes_rejected():
    with pytest.raises(BackendError, match="no usable votes"):
        soft_voting([], _ctx())


def test_completion_outside_space_rejected():
    votes = [MemberVote(backend="rogue", value="delta", probability=0.5,
                        distribution={}, weight=1.0)]
    with pytest.raises(BackendError, match="cannot complete"):
        soft_voting(votes, _ctx())


# --- boundary ----------------------------------------------------------------

def test_single_weight_dominates():
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.9, "beta": 0.1}),
        ConstantBackend("b", "beta", {"alpha": 0.1, "beta": 0.9}),
        ConstantBackend("c", "beta", {"alpha": 0.1, "beta": 0.9}),
    ]
    result = Ensemble(members, strategy="soft",
                      weights={"a": 10.0, "b": 1.0,
                               "c": 1.0}).evaluate({"x": 1}, TWO)
    # (10*0.9 + 0.1 + 0.1)/12 = 9.2/12
    assert result.value == "alpha"
    assert result.probability == pytest.approx(9.2 / 12)


def test_partial_weights_default_to_zero():
    # Members missing from the weights map get weight 0 (documented).
    members = [
        ConstantBackend("a", "alpha", {"alpha": 0.9, "beta": 0.1}),
        ConstantBackend("b", "beta", {"alpha": 0.1, "beta": 0.9}),
    ]
    result = Ensemble(members, strategy="soft",
                      weights={"a": 1.0}).evaluate({"x": 1}, TWO)
    assert result.value == "alpha"
    assert result.probability == pytest.approx(0.9)
