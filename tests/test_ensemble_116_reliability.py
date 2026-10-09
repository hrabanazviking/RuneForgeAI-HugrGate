"""Slice 116 — Backend reliability weighting.

Trust from evidence: the ReliabilityTracker converts labeled
outcomes into Laplace-smoothed member weights, and penalizes
correlated-error cliques so duplicated minds stop buying duplicate
influence.
"""

from __future__ import annotations

import pytest

from hugrgate.ensemble import (
    Ensemble,
    ReliabilityTracker,
    detect_correlated_errors,
)
from hugrgate.errors import PolicyError
from ensemble_fakes import CAT_SPEC, ConstantBackend

ALPHA = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
BETA = {"alpha": 0.2, "beta": 0.6, "gamma": 0.2}


# --- success -----------------------------------------------------------------

def test_new_members_start_at_half():
    tracker = ReliabilityTracker(["a", "b"])
    assert tracker.reliability("a") == pytest.approx(0.5)
    assert tracker.raw_accuracy("a") == 0.5
    assert tracker.weights() == pytest.approx({"a": 0.5, "b": 0.5})


def test_observations_move_reliability():
    tracker = ReliabilityTracker(["a", "b"])
    tracker.observe_many("a", [True] * 9 + [False])
    tracker.observe_many("b", [True] * 4 + [False] * 6)
    # Laplace: a = 10/12, b = 5/12
    assert tracker.reliability("a") == pytest.approx(10 / 12)
    assert tracker.reliability("b") == pytest.approx(5 / 12)
    assert tracker.raw_accuracy("a") == pytest.approx(0.9)
    w = tracker.weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["a"] > w["b"]
    assert w["a"] == pytest.approx((10 / 12) / (15 / 12))


def test_weights_drive_weighted_voting_end_to_end():
    tracker = ReliabilityTracker(["a", "b", "c"])
    tracker.observe_many("a", [True] * 9 + [False])       # reliable
    tracker.observe_many("b", [True] * 4 + [False] * 6)   # shaky
    tracker.observe_many("c", [True] * 4 + [False] * 6)   # shaky
    members = [ConstantBackend("a", "alpha", ALPHA),
               ConstantBackend("b", "beta", BETA),
               ConstantBackend("c", "beta", BETA)]
    ens = Ensemble(members, strategy="weighted",
                   weights=tracker.weights())
    result = ens.evaluate({"x": 1}, CAT_SPEC())
    # reliability: a=10/12, b=c=5/12 -> normalized a=0.5, b=c=0.25:
    # alpha 0.5 vs beta 0.5 -> tie -> earliest ballot (a) wins
    assert result.value == "alpha"


def test_correlation_report_penalizes_duplicates():
    tracker = ReliabilityTracker(["a", "b", "c"])
    tracker.observe_many("a", [True] * 8 + [False] * 2)
    tracker.observe_many("b", [True] * 8 + [False] * 2)
    tracker.observe_many("c", [True] * 5 + [False] * 5)
    hist = [True, True, False, True, False, False]
    report = detect_correlated_errors({"a": list(hist),
                                       "b": list(hist),
                                       "c": [True, False] * 3})
    assert report.cliques == [["a", "b"]]
    before = tracker.weights()
    tracker.apply_correlation_report(report, factor=0.5)
    after = tracker.weights()
    # a and b equally reliable: 'a' < 'b' keeps full weight (tie-break);
    # b is halved, so a outranks b and the weights still sum to 1.
    assert after["b"] < before["b"]
    assert after["a"] > after["b"]
    assert abs(sum(after.values()) - 1.0) < 1e-9
    tracker.clear_penalties()
    assert tracker.weights() == pytest.approx(before)


def test_penalize_validation():
    tracker = ReliabilityTracker(["a"])
    with pytest.raises(PolicyError, match="in \\[0,1\\]"):
        tracker.penalize("a", 1.5)
    with pytest.raises(PolicyError, match="unknown member"):
        tracker.penalize("zzz", 0.5)
    with pytest.raises(PolicyError, match="in \\[0,1\\]"):
        tracker.apply_correlation_report(
            detect_correlated_errors({"a": [True], "b": [True]}),
            factor=2.0)


def test_to_dict():
    tracker = ReliabilityTracker(["a"])
    tracker.observe("a", True)
    d = tracker.to_dict()
    assert d["reliabilities"]["a"] == pytest.approx(2 / 3)
    assert d["observations"] == {"a": 1}
    assert d["weights"]["a"] == pytest.approx(1.0)


# --- failure -----------------------------------------------------------------

def test_validation():
    with pytest.raises(PolicyError, match="at least one member"):
        ReliabilityTracker([])
    with pytest.raises(PolicyError, match="unique"):
        ReliabilityTracker(["a", "a"])
    with pytest.raises(PolicyError, match="smoothing must be > 0"):
        ReliabilityTracker(["a"], smoothing=0.0)
    with pytest.raises(PolicyError, match="unknown member"):
        ReliabilityTracker(["a"]).observe("zzz", True)
    with pytest.raises(PolicyError, match="unknown member"):
        ReliabilityTracker(["a"]).reliability("zzz")


def test_zero_total_weight_guarded():
    tracker = ReliabilityTracker(["a", "b"])
    tracker.penalize("a", 0.0)
    tracker.penalize("b", 0.0)
    with pytest.raises(PolicyError, match="sum to zero"):
        tracker.weights()


# --- boundary -----------------------------------------------------------------

def test_smoothing_strength_tunable():
    gentle = ReliabilityTracker(["a"], smoothing=0.1)
    strong = ReliabilityTracker(["a"], smoothing=10.0)
    gentle.observe("a", True)
    strong.observe("a", True)
    # less smoothing -> closer to the raw 1.0
    assert gentle.reliability("a") > strong.reliability("a")
    assert strong.reliability("a") == pytest.approx(11 / 21)
