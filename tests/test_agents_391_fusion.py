"""Slice 391 — agent confidence fusion."""

from __future__ import annotations

import pytest

from hugrgate.agents.fusion import (
    FUSION_METHODS,
    AgentVote,
    disagreement,
    fuse_confidences,
)


def _votes():
    return (
        AgentVote("a", "yes", 0.9, weight=2.0),
        AgentVote("b", "yes", 0.6, weight=1.0),
        AgentVote("c", "no", 0.8, weight=1.0),
    )


def test_weighted_fusion():
    r = fuse_confidences(_votes(), method="weighted")
    assert r.label == "yes"  # mass 2.4 vs 0.8
    assert r.confidence == pytest.approx((2 * 0.9 + 1 * 0.6) / 3)
    assert r.method == "weighted"
    assert r.votes == _votes()
    assert 0.0 < r.disagreement < 1.0


def test_weighted_heavy_minority_wins():
    votes = (AgentVote("a", "yes", 0.9, weight=1.0),
             AgentVote("b", "no", 0.9, weight=3.0))
    r = fuse_confidences(votes)
    assert r.label == "no"


def test_majority_ignores_weights():
    votes = (AgentVote("a", "yes", 0.5, weight=10.0),
             AgentVote("b", "no", 0.9, weight=1.0),
             AgentVote("c", "no", 0.9, weight=1.0))
    r = fuse_confidences(votes, method="majority")
    assert r.label == "no"
    assert r.confidence == pytest.approx(0.9)


def test_majority_tie_breaks_deterministically():
    votes = (AgentVote("b", "yes", 0.7), AgentVote("a", "no", 0.9))
    r = fuse_confidences(votes, method="majority")
    # 1-1 tie on counts -> higher total confidence wins -> "no"
    assert r.label == "no"
    votes = (AgentVote("b", "yes", 0.7), AgentVote("a", "no", 0.7))
    r = fuse_confidences(votes, method="majority")
    assert r.label == "no"  # full tie -> lexicographic


def test_max_conf():
    r = fuse_confidences(_votes(), method="max_conf")
    assert r.label == "yes" and r.confidence == pytest.approx(0.9)
    votes = (AgentVote("b", "no", 0.95), AgentVote("a", "yes", 0.9))
    assert fuse_confidences(votes, method="max_conf").label == "no"


def test_disagreement_scale():
    assert disagreement((AgentVote("a", "yes", 1.0),)) == 0.0
    d_split = disagreement((AgentVote("a", "yes", 0.9),
                            AgentVote("b", "no", 0.9)))
    assert d_split == pytest.approx(0.5)
    d_close = disagreement((AgentVote("a", "yes", 0.9),
                            AgentVote("b", "yes", 0.9),
                            AgentVote("c", "no", 0.1)))
    assert d_close < d_split
    with pytest.raises(ValueError):
        disagreement(())


def test_validation():
    with pytest.raises(ValueError):
        fuse_confidences(())
    with pytest.raises(ValueError):
        fuse_confidences(_votes(), method="vibes")
    with pytest.raises(ValueError):
        fuse_confidences((AgentVote("a", "yes", 0.5, weight=0.0),))
    with pytest.raises(ValueError):
        AgentVote("a", "yes", 1.5)
    with pytest.raises(ValueError):
        AgentVote("a", "yes", 0.5, weight=-1.0)
    with pytest.raises(ValueError):
        AgentVote("", "yes", 0.5)
    assert set(FUSION_METHODS) == {"weighted", "majority", "max_conf"}


def test_single_vote_fuses_to_itself():
    r = fuse_confidences((AgentVote("a", "maybe", 0.42),))
    assert (r.label, r.confidence, r.disagreement) == ("maybe", 0.42, 0.0)
