"""Slice 108 — Blending engine.

Convex member weights learned on holdout predictions by projected
gradient descent onto the simplex. Centerpiece: the blender finds
the best member and beats uniform averaging on holdout log-loss.
"""

from __future__ import annotations

import math

import pytest

from hugrgate import DecisionSpec
from hugrgate.ensemble import (
    Blender,
    Ensemble,
    blending_combine,
    log_loss,
    project_simplex,
)
from hugrgate.ensemble.base import MemberVote, StrategyContext
from hugrgate.errors import BackendError, PolicyError
from ensemble_fakes import ConstantBackend

BIN = DecisionSpec(type="binary", statement="s")


def _vote(name, value, pt):
    dist = {"true": pt, "false": 1 - pt} if value == "true" else \
        {"true": 1 - pt, "false": pt}
    return MemberVote(backend=name, value=value, probability=pt,
                      distribution=dist)


def _holdout(n=12):
    samples, labels = [], []
    for i in range(n):
        truth = "true" if i % 2 == 0 else "false"
        wrong = "false" if truth == "true" else "true"
        samples.append([_vote("good", truth, 0.85),
                        _vote("mid", truth, 0.6),
                        _vote("bad", wrong, 0.7)])
        labels.append(truth)
    return samples, labels


def _fitted():
    samples, labels = _holdout()
    return Blender(["good", "mid", "bad"]).fit(samples, labels, BIN)


# --- success -----------------------------------------------------------------

def test_blender_finds_the_best_member():
    blender = _fitted()
    assert blender.fitted
    w = blender.weights
    assert w["good"] > 0.9
    assert w["mid"] < 0.1 and w["bad"] < 0.1
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(x >= 0 for x in w.values())


def test_blended_log_loss_beats_uniform():
    samples, labels = _holdout()
    blender = Blender(["good", "mid", "bad"]).fit(samples, labels, BIN)
    assert blender.holdout_log_loss < 0.17  # ≈ -log(0.85)
    # uniform average: (0.85 + 0.6 + 0.3)/3 = 0.5833 on the truth
    uniform_ll = -math.log((0.85 + 0.6 + 0.3) / 3)
    assert blender.holdout_log_loss < uniform_ll


def test_fit_is_deterministic():
    samples, labels = _holdout()
    b1 = Blender(["good", "mid", "bad"]).fit(samples, labels, BIN)
    b2 = Blender(["good", "mid", "bad"]).fit(samples, labels, BIN)
    assert b1.weights == b2.weights


def test_blending_combine_end_to_end():
    blender = _fitted()
    members = [ConstantBackend("good", "true",
                               {"true": 0.85, "false": 0.15}),
               ConstantBackend("mid", "false",
                               {"true": 0.4, "false": 0.6}),
               ConstantBackend("bad", "false",
                               {"true": 0.3, "false": 0.7})]
    ens = Ensemble(members, strategy="blending").attach(blender)
    result = ens.evaluate({"x": 1}, BIN)
    # blender trusts "good" almost entirely
    assert result.value == "true"
    assert result.probability > 0.8
    meta = result.metadata["ensemble"]
    assert meta["strategy"] == "blending"
    assert meta["blend_weights"]["good"] > 0.9


def test_project_simplex_unit():
    assert project_simplex([0.5, 0.5]) == pytest.approx([0.5, 0.5])
    assert project_simplex([0.6, 0.6, 0.6]) == pytest.approx(
        [1 / 3, 1 / 3, 1 / 3])
    # [1.2, 0.3, -0.5] -> [0.95, 0.05, 0.0]: nearer than [1, 0, 0]
    # (0.375 < 0.38 squared distance), so this is the true projection.
    assert project_simplex([1.2, 0.3, -0.5]) == pytest.approx(
        [0.95, 0.05, 0.0])
    assert project_simplex([2.0, -1.0, 0.5]) == pytest.approx(
        [1.0, 0.0, 0.0])
    with pytest.raises(PolicyError, match="non-empty"):
        project_simplex([])


def test_log_loss_unit():
    assert log_loss({"a": 0.25}, "a") == pytest.approx(-math.log(0.25))
    assert math.isfinite(log_loss({"a": 0.0}, "a"))


# --- failure -----------------------------------------------------------------

def test_combine_needs_fitted_blender():
    votes = [_vote("good", "true", 0.85)]
    with pytest.raises(BackendError, match="fitted Blender"):
        blending_combine(votes, StrategyContext(spec=BIN, fitted=None))
    with pytest.raises(BackendError, match="fitted Blender"):
        blending_combine(votes, StrategyContext(
            spec=BIN, fitted=Blender(["good"])))


def test_blend_before_fit():
    with pytest.raises(BackendError, match="before fit"):
        Blender(["good"]).blend([_vote("good", "true", 0.9)], BIN)
    with pytest.raises(BackendError, match="before fit"):
        Blender(["good"]).weights  # noqa: B018


def test_fit_validation():
    samples, labels = _holdout()
    with pytest.raises(PolicyError, match="labels"):
        Blender(["good"]).fit(samples, labels[:-1], BIN)
    with pytest.raises(PolicyError, match="outside the spec space"):
        Blender(["good"]).fit(samples, ["maybe"] * len(labels), BIN)
    with pytest.raises(PolicyError, match="labeled samples"):
        Blender(["good"]).fit([], [], BIN)
    with pytest.raises(PolicyError, match="unique"):
        Blender(["a", "a"])
    with pytest.raises(PolicyError, match="at least one member"):
        Blender([])
    with pytest.raises(PolicyError, match="lr"):
        Blender(["a"], lr=0.0)
    with pytest.raises(PolicyError, match="iters"):
        Blender(["a"], iters=0)


def test_numeric_spec_rejected():
    numeric = DecisionSpec(type="numeric", minimum=0.0, maximum=1.0)
    with pytest.raises(BackendError, match="discrete spec"):
        blending_combine([], StrategyContext(spec=numeric,
                                             fitted=_fitted()))


# --- boundary ----------------------------------------------------------------

def test_single_member_blend_is_identity():
    samples = [[_vote("solo", "true", 0.7)] for _ in range(4)]
    labels = ["true"] * 4
    blender = Blender(["solo"]).fit(samples, labels, BIN)
    assert blender.weights == {"solo": 1.0}
    out = blender.blend([_vote("solo", "true", 0.7)], BIN)
    assert out == pytest.approx({"true": 0.7, "false": 0.3})


def test_spec_space_mismatch_rejected():
    blender = _fitted()
    two = DecisionSpec(type="categorical", options=["yes", "no"])
    with pytest.raises(BackendError, match="differs from the fitted"):
        blender.blend([_vote("good", "true", 0.9)], two)
