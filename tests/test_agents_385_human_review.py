"""Slice 385 — human-review routing."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.human_review import (
    TIMEOUT_POLICIES,
    HumanReviewQueue,
    ReviewItem,
)
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import HumanReviewTimeout


def _queue(**kw):
    clock = [1000.0]
    kw.setdefault("clock", lambda: clock[0])
    q = HumanReviewQueue(**kw)
    return q, clock


def _item(iid, **kw):
    base = dict(item_id=iid, ticket_id="t1", agent_id="a1",
                summary="approve deploy?", severity="warning", sla_s=60.0)
    base.update(kw)
    return ReviewItem(**base)


def test_enqueue_decide_lifecycle():
    q, _ = _queue()
    q.enqueue(_item("r1", severity="info"))
    q.enqueue(_item("r2", severity="critical"))
    pending = q.pending()
    assert [i.item_id for i in pending] == ["r2", "r1"]  # severity first
    d = q.decide("r2", True, "volmarr", note="looks right")
    assert d.approved and d.reviewer == "volmarr"
    assert q.decision_for("r2") is d
    assert [i.item_id for i in q.pending()] == ["r1"]
    with pytest.raises(ValueError):
        q.decide("r2", False, "volmarr")  # already decided
    with pytest.raises(ValueError):
        q.decide("nope", True, "volmarr")
    s = q.stats()
    assert s["enqueued"] == 2 and s["decided"] == 1 and s["approved"] == 1


def test_duplicate_enqueue_and_validation():
    q, _ = _queue()
    q.enqueue(_item("r1"))
    with pytest.raises(ValueError):
        q.enqueue(_item("r1"))
    with pytest.raises(ValueError):
        ReviewItem(item_id="x", ticket_id="t", agent_id="a",
                   summary="s", severity="nope")
    with pytest.raises(ValueError):
        ReviewItem(item_id="x", ticket_id="t", agent_id="a",
                   summary="s", sla_s=0)
    with pytest.raises(ValueError):
        q.decide("r1", True, "  ")


def test_overdue_detection():
    q, clock = _queue()
    q.enqueue(_item("r1", sla_s=60.0))
    q.enqueue(_item("r2", sla_s=3600.0))
    assert q.overdue() == ()
    clock[0] += 61.0
    overdue = q.overdue()
    assert [i.item_id for i in overdue] == ["r1"]


def test_sweep_auto_deny_and_approve():
    q, clock = _queue()
    q.enqueue(_item("r1", sla_s=10.0))
    clock[0] += 11.0
    assert q.sweep(on_timeout="auto_deny") == ()
    d = q.decision_for("r1")
    assert d is not None and not d.approved
    assert d.reviewer == "timeout-policy"
    assert q.pending() == ()

    q2, clock2 = _queue()
    q2.enqueue(_item("r2", sla_s=10.0))
    clock2[0] += 11.0
    q2.sweep(on_timeout="auto_approve")
    assert q2.decision_for("r2").approved is True


def test_sweep_raise_and_escalate():
    q, clock = _queue()
    q.enqueue(_item("r1", sla_s=10.0))
    q.enqueue(_item("r2", sla_s=10.0))
    clock[0] += 11.0
    with pytest.raises(HumanReviewTimeout) as ei:
        q.sweep(on_timeout="raise")
    assert ei.value.code == "human_review_timeout"
    assert ei.value.details["item_ids"] == ["r1", "r2"]
    assert len(q.pending()) == 2  # still pending

    left = q.sweep(on_timeout="escalate")
    assert [i.item_id for i in left] == ["r1", "r2"]
    assert len(q.pending()) == 2
    with pytest.raises(ValueError):
        q.sweep(on_timeout="nap")


def test_bus_lifecycle_signals():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("review.*", seen.append)
    q, clock = _queue(bus=bus)
    q.enqueue(_item("r1", sla_s=10.0,
                    metadata={"trace_id": "hg-trace-00000007"}))
    q.decide("r1", False, "volmarr")
    topics = [s.topic for s in seen]
    assert topics == ["review.enqueued", "review.decided"]
    assert seen[0].trace_id == "hg-trace-00000007"  # trace continuity

    q.enqueue(_item("r2", sla_s=10.0))
    clock[0] += 11.0
    q.sweep(on_timeout="escalate")
    assert seen[-1].topic == "review.overdue"


def test_timeout_policies_constant():
    assert set(TIMEOUT_POLICIES) == {"escalate", "auto_deny",
                                     "auto_approve", "raise"}
