"""Slice 383 — attention prioritization."""

from __future__ import annotations

import pytest

from hugrgate.agents.attention import (
    AttentionConfig,
    AttentionItem,
    AttentionPrioritizer,
)


def _item(iid, **kw):
    base = dict(item_id=iid, topic="t", priority="normal",
                urgency=0.5, novelty=0.5, cost=0.5)
    base.update(kw)
    return AttentionItem(**base)


def test_score_orders_by_inputs():
    ap = AttentionPrioritizer()
    crit = _item("c", priority="critical", urgency=1.0)
    low = _item("l", priority="low", urgency=0.0, cost=1.0)
    assert ap.score(crit) > ap.score(low)
    ap.push(low)
    ap.push(crit)
    assert ap.pop().item_id == "c"
    assert ap.pop().item_id == "l"
    assert ap.pop() is None


def test_cost_penalty_and_novelty_reward():
    ap = AttentionPrioritizer()
    cheap = _item("cheap", cost=0.0, novelty=0.0)
    dear = _item("dear", cost=1.0, novelty=0.0)
    new = _item("new", cost=0.5, novelty=1.0)
    assert ap.score(cheap) > ap.score(dear)
    assert ap.score(new) > ap.score(_item("old", cost=0.5, novelty=0.0))


def test_tie_break_is_deterministic_fifo():
    clock = [0.0]
    ap = AttentionPrioritizer(clock=lambda: clock[0])
    ap.push(_item("a"))
    clock[0] += 1.0
    ap.push(_item("b"))
    assert ap.peek().item_id == "a"  # peek does not remove
    assert len(ap) == 2
    assert ap.pop().item_id == "a"
    assert ap.pop().item_id == "b"


def test_overflow_sheds_lowest():
    ap = AttentionPrioritizer(AttentionConfig(max_items=2))
    ap.push(_item("low1", priority="low"))
    ap.push(_item("low2", priority="low"))
    shed = ap.push(_item("hi", priority="critical"))
    assert shed in ("low1", "low2")
    assert len(ap) == 2
    assert ap.pop().item_id == "hi"
    assert ap.stats()["dropped_overflow"] == 1


def test_overflow_sheds_self_when_worst():
    ap = AttentionPrioritizer(AttentionConfig(max_items=1))
    ap.push(_item("hi", priority="critical"))
    assert ap.push(_item("lo", priority="low")) == "shed-self"
    assert len(ap) == 1
    assert ap.pop().item_id == "hi"


def test_reprioritize_moves_item():
    ap = AttentionPrioritizer()
    ap.push(_item("a", urgency=0.0))
    ap.push(_item("b", urgency=0.0))
    assert ap.reprioritize("b", urgency=1.0) is True
    assert ap.pop().item_id == "b"
    assert ap.reprioritize("ghost", urgency=1.0) is False
    assert ap.stats()["reprioritized"] == 1


def test_validation():
    with pytest.raises(ValueError):
        AttentionConfig(max_items=0)
    with pytest.raises(ValueError):
        AttentionConfig(w_cost=-1.0)
    with pytest.raises(ValueError):
        AttentionItem(item_id="", topic="t")
    with pytest.raises(ValueError):
        AttentionItem(item_id="x", topic="t", priority="nope")
    with pytest.raises(ValueError):
        AttentionItem(item_id="x", topic="t", urgency=2.0)
    ap = AttentionPrioritizer()
    ap.push(_item("a"))
    with pytest.raises(ValueError):
        ap.push(_item("a"))


def test_stats_and_ladder():
    ap = AttentionPrioritizer()
    ap.push(_item("a"))
    ap.pop()
    s = ap.stats()
    assert s == {"pushed": 1, "popped": 1, "dropped_overflow": 0,
                 "reprioritized": 0}
    assert ap.priorities() == ("low", "normal", "high", "critical")
