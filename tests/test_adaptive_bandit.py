"""Slice 130 — contextual bandit adapter tests."""

from __future__ import annotations

import pytest

from hugrgate.adaptive.bandit import (
    BanditDecision,
    ContextualBanditAdapter,
    _solve,
)
from hugrgate.errors import BackendError, SpecError

NAMES = ["x0", "x1", "bias"]


def bandit(**kw):
    params = {"alpha": 1.0, "ridge": 1.0}
    params.update(kw)
    return ContextualBanditAdapter(NAMES, **params)


# --- success ---------------------------------------------------------------

def test_initial_select_prefers_nothing_deterministically():
    b = bandit(alpha=0.0)  # no exploration bonus: all arms score 0
    d = b.select({"x0": 1.0, "x1": 0.0, "bias": 1.0}, ["b_arm", "a_arm"])
    assert isinstance(d, BanditDecision)
    assert d.arm == "a_arm"  # tie -> name order
    assert d.expected_reward == 0.0

def test_bandit_learns_contextual_preference():
    b = bandit(alpha=0.5)
    # arm_good is great when x0=1, terrible when x0=0; arm_bad reversed.
    for _ in range(20):
        b.update("arm_good", {"x0": 1.0, "x1": 0.0, "bias": 1.0}, 1.0)
        b.update("arm_good", {"x0": 0.0, "x1": 0.0, "bias": 1.0}, 0.0)
        b.update("arm_bad", {"x0": 1.0, "x1": 0.0, "bias": 1.0}, 0.0)
        b.update("arm_bad", {"x0": 0.0, "x1": 0.0, "bias": 1.0}, 1.0)
    d_hi = b.select({"x0": 1.0, "x1": 0.0, "bias": 1.0},
                    ["arm_good", "arm_bad"])
    d_lo = b.select({"x0": 0.0, "x1": 0.0, "bias": 1.0},
                    ["arm_good", "arm_bad"])
    assert d_hi.arm == "arm_good"
    assert d_lo.arm == "arm_bad"

def test_ucb_explores_untried_arm():
    b = bandit(alpha=2.0)
    for _ in range(10):
        b.update("tried", {"x0": 1.0, "x1": 0.0, "bias": 1.0}, 0.9)
    d = b.select({"x0": 1.0, "x1": 0.0, "bias": 1.0}, ["tried", "fresh"])
    assert d.arm == "fresh"  # wide interval beats a known 0.9
    assert d.per_arm["fresh"] > d.per_arm["tried"]

def test_seed_prior_biases_cold_start():
    b = bandit(alpha=0.0)
    b.seed_prior("newbie", [0.3, 0.3, 0.3], strength=5.0)
    assert b.expected_reward("newbie",
                            {"x0": 1.0, "x1": 1.0, "bias": 1.0}) > 0.0
    assert b.expected_reward("stranger",
                             {"x0": 1.0, "x1": 1.0, "bias": 1.0}) == 0.0

def test_serialization_round_trip_preserves_behavior():
    b = bandit()
    b.update("a", {"x0": 1.0, "x1": 0.0, "bias": 1.0}, 0.8)
    b.update("b", {"x0": 0.0, "x1": 1.0, "bias": 1.0}, 0.4)
    data = b.to_dict()
    assert data["schema"] == "adaptive-bandit/v1"
    b2 = ContextualBanditAdapter.from_dict(data)
    f = {"x0": 1.0, "x1": 0.0, "bias": 1.0}
    assert b2.select(f, ["a", "b"]).arm == b.select(f, ["a", "b"]).arm
    assert b2.arm_stats("a")["n"] == 1
    assert b2.arm_stats("ghost")["n"] == 0

def test_arm_stats_tracks_means():
    b = bandit()
    b.update("a", {"x0": 1.0, "x1": 0.0, "bias": 1.0}, 0.6)
    b.update("a", {"x0": 1.0, "x1": 0.0, "bias": 1.0}, 1.0)
    assert b.arm_stats("a")["mean_reward"] == pytest.approx(0.8)

def test_solver_handles_known_system():
    x = _solve([[2.0, 1.0], [1.0, 3.0]], [5.0, 6.0])
    assert x[0] == pytest.approx(1.8) and x[1] == pytest.approx(1.4)

# --- failure ---------------------------------------------------------------

def test_empty_feature_names_rejected():
    with pytest.raises(SpecError):
        ContextualBanditAdapter([])

def test_duplicate_feature_names_rejected():
    with pytest.raises(SpecError):
        ContextualBanditAdapter(["x", "x"])

def test_bad_hyperparameters_rejected():
    with pytest.raises(SpecError):
        ContextualBanditAdapter(NAMES, alpha=-1.0)
    with pytest.raises(SpecError):
        ContextualBanditAdapter(NAMES, ridge=0.0)

def test_select_needs_arms():
    with pytest.raises(SpecError):
        bandit().select({"x0": 1, "x1": 0, "bias": 1}, [])

def test_duplicate_arms_rejected():
    with pytest.raises(SpecError):
        bandit().select({"x0": 1, "x1": 0, "bias": 1}, ["a", "a"])

def test_missing_feature_column_rejected():
    with pytest.raises(SpecError):
        bandit().select({"x0": 1.0}, ["a"])

def test_nonfinite_reward_rejected():
    with pytest.raises(SpecError):
        bandit().update("a", {"x0": 1, "x1": 0, "bias": 1}, float("nan"))

def test_bad_weight_rejected():
    with pytest.raises(SpecError):
        bandit().update("a", {"x0": 1, "x1": 0, "bias": 1}, 0.5, weight=0.0)

def test_singular_system_raises_not_garbage():
    with pytest.raises(BackendError):
        _solve([[0.0, 0.0], [0.0, 0.0]], [1.0, 2.0])

def test_wrong_schema_rejected():
    with pytest.raises(SpecError):
        ContextualBanditAdapter.from_dict({"schema": "nope"})

def test_seed_prior_dim_mismatch_rejected():
    with pytest.raises(SpecError):
        bandit().seed_prior("a", [1.0, 2.0])
