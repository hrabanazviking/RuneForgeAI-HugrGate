"""Slice 123 — Ensemble adversarial tests.

Deterministic sabotage: dropout, corruption, abstention waves, tie
storms, slow members. The council must decide correctly, degrade
gracefully, or refuse honestly — never crash, never silently
corrupt.
"""

from __future__ import annotations

import pytest
from ensemble_fakes import CAT_SPEC, ConstantBackend

from hugrgate.ensemble import (
    AbstainBackend,
    AdversarialCase,
    CorruptBackend,
    DropoutBackend,
    Ensemble,
    SlowBackend,
    run_adversarial_suite,
    tie_storm_members,
)
from hugrgate.errors import PolicyError

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}
STATES = [{"x": i} for i in range(4)]


def _council(*members, strategy="hard", **kw):
    return Ensemble(list(members), strategy=strategy, **kw)


# --- success -----------------------------------------------------------------

def test_dropout_member_isolated():
    members = [DropoutBackend(ConstantBackend("a", "alpha", ALPHA),
                              every=1),  # always dies
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "alpha", ALPHA)]
    case = AdversarialCase("dropout", _council(*members), STATES,
                           CAT_SPEC())
    (summary,) = run_adversarial_suite([case]).values()
    assert summary["decided"] == 4
    assert summary["values"] == ["alpha"] * 4
    assert summary["errors"] == []
    assert summary["min_usable_votes"] == 2
    assert any("backend_error" in r for r in summary["skip_reasons"])


def test_intermittent_dropout():
    members = [DropoutBackend(ConstantBackend("a", "alpha", ALPHA),
                              every=2),  # dies every other call
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "beta", BETA)]
    case = AdversarialCase("flaky", _council(*members), STATES,
                           CAT_SPEC())
    (summary,) = run_adversarial_suite([case]).values()
    assert summary["decided"] == 4
    assert summary["values"] == ["alpha"] * 4  # b+c carry the vote
    assert members[0].sabotaged == 2  # deterministic count


def test_corrupt_ballots_rejected():
    members = [CorruptBackend(ConstantBackend("a", "beta", BETA),
                              every=1),
               ConstantBackend("b", "alpha", ALPHA),
               ConstantBackend("c", "alpha", ALPHA)]
    case = AdversarialCase("corrupt", _council(*members), STATES,
                           CAT_SPEC())
    (summary,) = run_adversarial_suite([case]).values()
    assert summary["decided"] == 4
    assert summary["values"] == ["alpha"] * 4
    assert any("invalid_result" in r for r in summary["skip_reasons"])


def test_abstention_wave_refuses_honestly():
    members = [AbstainBackend(ConstantBackend("a", "alpha", ALPHA),
                              every=1),
               AbstainBackend(ConstantBackend("b", "alpha", ALPHA),
                              every=1)]
    case = AdversarialCase("abstain-wave",
                           _council(*members, min_members=1),
                           STATES, CAT_SPEC())
    (summary,) = run_adversarial_suite([case]).values()
    assert summary["decided"] == 0
    assert len(summary["errors"]) == 4  # BackendError per state
    assert all("usable votes" in e for e in summary["errors"])
    assert not any(e.startswith("UNEXPECTED")
                   for e in summary["errors"])


def test_tie_storm_uses_documented_tiebreak():
    # 4 members, 2-2 split -> break_tie: earliest ballot wins ("m0")
    members = tie_storm_members(4, ["alpha", "beta"], ALPHA)
    case = AdversarialCase("tie-storm", _council(*members), STATES,
                           CAT_SPEC())
    (summary,) = run_adversarial_suite([case]).values()
    assert summary["decided"] == 4
    assert summary["values"] == ["alpha"] * 4  # m0 votes alpha


def test_slow_member_does_not_block():
    members = [SlowBackend(ConstantBackend("a", "alpha", ALPHA),
                           delay_seconds=0.01),
               ConstantBackend("b", "alpha", ALPHA)]
    case = AdversarialCase("slow", _council(*members), STATES,
                           CAT_SPEC())
    (summary,) = run_adversarial_suite([case]).values()
    assert summary["decided"] == 4
    assert summary["values"] == ["alpha"] * 4


def test_suite_runs_many_cases():
    cases = [
        AdversarialCase("dropout",
                        _council(DropoutBackend(
                            ConstantBackend("a", "alpha", ALPHA)),
                            ConstantBackend("b", "alpha", ALPHA)),
                        STATES, CAT_SPEC()),
        AdversarialCase("tie",
                        _council(*tie_storm_members(
                            4, ["alpha", "beta"], ALPHA)),
                        STATES, CAT_SPEC()),
    ]
    report = run_adversarial_suite(cases)
    assert set(report) == {"dropout", "tie"}
    assert report["dropout"]["values"] == ["alpha"] * 4
    assert report["tie"]["values"] == ["alpha"] * 4


# --- failure -----------------------------------------------------------------

def test_saboteur_validation():
    with pytest.raises(PolicyError, match="every must be"):
        DropoutBackend(ConstantBackend("a", "alpha", ALPHA), every=0)
    with pytest.raises(PolicyError, match="delay_seconds"):
        SlowBackend(ConstantBackend("a", "alpha", ALPHA),
                    delay_seconds=-1.0)
    with pytest.raises(PolicyError, match="tie storm needs"):
        tie_storm_members(1, ["alpha", "beta"], ALPHA)
    with pytest.raises(PolicyError, match="needs cases"):
        run_adversarial_suite([])
    with pytest.raises(PolicyError, match="unique"):
        case = AdversarialCase("dup", _council(
            ConstantBackend("a", "alpha", ALPHA)), STATES,
            CAT_SPEC())
        run_adversarial_suite([case, case])


# --- boundary -----------------------------------------------------------------

def test_every_one_means_always():
    sab = DropoutBackend(ConstantBackend("a", "alpha", ALPHA),
                         every=1)
    for _ in range(3):
        with pytest.raises(Exception):
            sab.evaluate({"x": 1}, CAT_SPEC())
    assert sab.calls == 3 and sab.sabotaged == 3
