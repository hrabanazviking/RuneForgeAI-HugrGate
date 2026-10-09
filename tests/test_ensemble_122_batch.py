"""Slice 122 — Ensemble batch mode.

One member.batch() call per member for the whole batch, then
per-state combination identical to evaluate() — including fault
isolation and the consensus option.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import Ensemble, batch_collect_votes
from hugrgate.errors import BackendError, PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend, ScriptedBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


class FastBackend(ConstantBackend):
    """A member with a real batch fast path."""

    def __init__(self, name, value, distribution):
        super().__init__(name, value, distribution)
        self.batch_calls = 0

    def batch(self, states, spec, context=None):
        self.batch_calls += 1
        return [self.evaluate(s, spec, context) for s in states]


class BrokenBatchBackend(ConstantBackend):
    """batch() explodes; per-state evaluate still works."""

    def batch(self, states, spec, context=None):
        raise RuntimeError("batch path is down")


class ShortBatchBackend(ConstantBackend):
    """batch() returns the wrong number of results."""

    def batch(self, states, spec, context=None):
        return [self.evaluate(states[0], spec, context)]


def _states(n=4):
    return [{"x": i} for i in range(n)]


# --- success -----------------------------------------------------------------

def test_batch_uses_member_fast_path_once():
    members = [FastBackend("a", "alpha", ALPHA),
               FastBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="soft")
    results = ens.decide_batch(_states(), CAT_SPEC())
    assert [r.value for r in results] == ["alpha"] * 4
    for m in members:
        assert m.batch_calls == 1  # one batch call, not 4 evaluates


def test_batch_matches_single_evaluates():
    members = [FastBackend("a", "alpha", ALPHA),
               FastBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="weighted",
                   weights={"a": 2.0, "b": 1.0})
    states = _states(3)
    batched = ens.decide_batch(states, CAT_SPEC())
    singles = [ens.evaluate(s, CAT_SPEC()) for s in states]
    for b, s in zip(batched, singles):
        assert b.value == s.value
        assert b.probability == pytest.approx(s.probability)
        assert b.distribution == pytest.approx(s.distribution)
        assert b.backend == s.backend == "ensemble[weighted]"


def test_batch_fallback_when_member_batch_raises():
    members = [BrokenBatchBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "alpha", ALPHA)]
    ens = Ensemble(members, strategy="hard")
    results = ens.decide_batch(_states(3), CAT_SPEC())
    assert [r.value for r in results] == ["alpha"] * 3
    # per-state isolation: 'a' still voted in every state
    for r in results:
        assert r.metadata["ensemble"]["usable_votes"] == 2


def test_batch_length_mismatch_skips_member():
    members = [ShortBatchBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="hard")
    results = ens.decide_batch(_states(3), CAT_SPEC())
    assert [r.value for r in results] == ["beta"] * 3
    for r in results:
        ballots = r.metadata["ensemble"]["member_votes"]
        skipped = [b for b in ballots if b["skipped"]]
        assert len(skipped) == 1
        assert "batch_length_mismatch" in skipped[0]["skip_reason"]


def test_batch_preserves_per_state_fault_isolation():
    from hugrgate.result import DecisionResult
    bad_member = ScriptedBackend("flaky", [
        DecisionResult(value="alpha", probability=0.7,
                       distribution=dict(ALPHA)),
        DecisionResult(value=None, probability=0.0, distribution={}),
        DecisionResult(value="alpha", probability=0.7,
                       distribution=dict(ALPHA)),
    ])
    ens = Ensemble([bad_member, ConstantBackend("good", "alpha",
                                                ALPHA)],
                   strategy="hard")
    results = ens.decide_batch(_states(3), CAT_SPEC())
    assert [r.value for r in results] == ["alpha"] * 3
    mid = results[1].metadata["ensemble"]["member_votes"]
    flaky = next(b for b in mid if b["backend"] == "flaky")
    assert flaky["skipped"] is True
    assert "abstained_result" in flaky["skip_reason"]


def test_batch_applies_consensus_per_state():
    from hugrgate.ensemble import ConsensusConfig
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="hard",
                   strategy_options={
                       "consensus": ConsensusConfig(
                           min_agreement=0.99)})
    results = ens.decide_batch(_states(2), CAT_SPEC())
    assert all(r.value is None for r in results)  # 1/2 < 0.99
    assert all(r.accepted is False for r in results)


def test_batch_collect_votes_empty():
    members = [ConstantBackend("a", "alpha", ALPHA)]
    assert batch_collect_votes(members, [], CAT_SPEC()) == []
    assert Ensemble(members).decide_batch([], CAT_SPEC()) == []


# --- failure -----------------------------------------------------------------

def test_batch_min_members_per_state():
    members = [ConstantBackend("a", "alpha", ALPHA)]
    ens = Ensemble(members, strategy="hard", min_members=2)
    with pytest.raises(BackendError, match="batch state 0"):
        ens.decide_batch(_states(2), CAT_SPEC())


def test_batch_collect_votes_validation():
    members = [ConstantBackend("a", "alpha", ALPHA)]
    with pytest.raises(PolicyError, match="min_members"):
        batch_collect_votes(members, _states(1), CAT_SPEC(),
                            min_members=0)


# --- boundary -----------------------------------------------------------------

def test_single_state_batch_matches_evaluate():
    members = [FastBackend("a", "alpha", ALPHA),
               FastBackend("b", "beta", BETA)]
    ens = Ensemble(members, strategy="soft")
    (one,) = ens.decide_batch([{"x": 0}], CAT_SPEC())
    single = ens.evaluate({"x": 0}, CAT_SPEC())
    assert one.value == single.value
    assert one.distribution == pytest.approx(single.distribution)
