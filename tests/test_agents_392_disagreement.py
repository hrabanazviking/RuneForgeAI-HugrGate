"""Slice 392 — agent disagreement handling."""

from __future__ import annotations

import pytest

from hugrgate.agents.disagreement import (
    DISAGREEMENT_STRATEGIES,
    DisagreementResolver,
)
from hugrgate.agents.fusion import AgentVote
from hugrgate.agents.human_review import HumanReviewQueue


def _split():
    return (AgentVote("a", "yes", 0.9), AgentVote("b", "no", 0.9))


def _consensus():
    return (AgentVote("a", "yes", 0.9), AgentVote("b", "yes", 0.8),
            AgentVote("c", "yes", 0.7))


def test_fuse_escalates_on_split_not_on_consensus():
    r = DisagreementResolver(disagreement_threshold=0.4)
    res = r.resolve(_split(), strategy="fuse")
    assert res.escalated is True
    assert "exceeds threshold" in res.reason
    assert res.fusion is not None
    res = r.resolve(_consensus(), strategy="fuse")
    assert res.escalated is False
    assert res.label == "yes"
    assert "within threshold" in res.reason


def test_threshold_is_the_honesty_knob():
    mild = (AgentVote("a", "yes", 0.9), AgentVote("b", "yes", 0.8),
            AgentVote("c", "no", 0.4))
    strict = DisagreementResolver(disagreement_threshold=0.0)
    assert strict.resolve(mild).escalated is True  # any dissent
    lax = DisagreementResolver(disagreement_threshold=1.0)
    assert lax.resolve(_split()).escalated is False  # never
    with pytest.raises(ValueError):
        DisagreementResolver(disagreement_threshold=2.0)


def test_other_strategies():
    r = DisagreementResolver()
    res = r.resolve(_split(), strategy="majority")
    assert res.strategy == "majority" and res.escalated is True
    res = r.resolve(_split(), strategy="highest_confidence")
    assert res.strategy == "highest_confidence"
    assert res.label == "yes"  # tie 0.9/0.9 -> agent id order
    with pytest.raises(ValueError):
        r.resolve(_split(), strategy="vibes")


def test_human_review_strategy():
    q = HumanReviewQueue()
    r = DisagreementResolver(review_queue=q)
    res = r.resolve(_split(), strategy="human_review",
                    ticket_id="t9", agent_id="arbiter")
    assert res.escalated is True and res.label == ""
    assert res.review_item_id == "disagree-t9"
    assert len(q.pending()) == 1
    item = q.pending()[0]
    assert "a=yes(0.90)" in item.summary
    s = r.stats()
    assert s == {"resolved": 1, "escalated": 1, "human_reviewed": 1}


def test_human_review_needs_queue_and_votes():
    r = DisagreementResolver()
    with pytest.raises(ValueError):
        r.resolve(_split(), strategy="human_review")
    q = HumanReviewQueue()
    r2 = DisagreementResolver(review_queue=q)
    with pytest.raises(ValueError):
        r2.resolve((), strategy="human_review")


def test_stats():
    r = DisagreementResolver()
    r.resolve(_split())
    r.resolve(_consensus())
    s = r.stats()
    assert s["resolved"] == 2 and s["escalated"] == 1
    assert set(DISAGREEMENT_STRATEGIES) == {"fuse", "majority",
                                            "highest_confidence",
                                            "human_review"}
