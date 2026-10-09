"""Slice 389 — agent cost routing."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.cost import CostRouter
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentNotFound


def test_cost_and_budget_ledger():
    r = CostRouter()
    r.set_cost("a", 0.5)
    r.set_budget("a", 1.0)
    led = r.ledger("a")
    assert led.cost_per_decision == 0.5
    assert led.remaining == 1.0 and not led.exhausted
    r.spend("a", 0.6)
    led = r.ledger("a")
    assert led.spent == pytest.approx(0.6)
    assert led.remaining == pytest.approx(0.4)
    assert not r.authorize("a", 0.5)
    assert r.authorize("a", 0.4)
    r.spend("a", 0.4)
    assert r.ledger("a").exhausted
    assert not r.authorize("a", 0.0)


def test_unbounded_budget_and_unknown_cost():
    r = CostRouter()
    assert r.authorize("ghost", 999.0)  # no budget: always fits
    led = r.ledger("ghost")
    assert led.budget is None and led.remaining is None
    import math
    assert led.cost_per_decision == math.inf


def test_exhaustion_signal_edge_triggered():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("cost.budget_exhausted", seen.append)
    r = CostRouter(bus=bus)
    r.set_budget("a", 1.0)
    r.spend("a", 0.5)
    assert seen == []
    r.spend("a", 0.5)
    assert len(seen) == 1
    assert seen[0].payload["agent_id"] == "a"
    r.spend("a", 0.1)  # still exhausted: no second signal
    assert len(seen) == 1


def test_pick_cheapest():
    r = CostRouter()
    r.set_cost("dear", 5.0)
    r.set_cost("cheap", 1.0)
    r.set_cost("mid", 2.0)
    assert r.pick_cheapest(["dear", "cheap", "mid"]) == "cheap"
    assert r.pick_cheapest(["dear", "mid"], max_cost=3.0) == "mid"
    # Unknown cost sorts as +inf: never preferred over priced.
    assert r.pick_cheapest(["ghost", "cheap"]) == "cheap"
    assert r.pick_cheapest(["ghost"]) == "ghost"  # only candidate
    with pytest.raises(AgentNotFound):
        r.pick_cheapest(["dear"], max_cost=1.0)
    with pytest.raises(ValueError):
        r.pick_cheapest([])


def test_pick_cheapest_tie_break():
    r = CostRouter()
    r.set_cost("b", 1.0)
    r.set_cost("a", 1.0)
    assert r.pick_cheapest(["b", "a"]) == "a"


def test_budget_reset_clears_exhaustion():
    r = CostRouter()
    r.set_budget("a", 1.0)
    r.spend("a", 1.0)
    assert r.ledger("a").exhausted
    r.set_budget("a", 5.0)  # top-up resets the edge trigger
    assert not r.ledger("a").exhausted
    assert r.authorize("a", 3.0)
    r.set_budget("a", None)  # unbounded
    assert r.ledger("a").budget is None


def test_validation():
    r = CostRouter()
    with pytest.raises(ValueError):
        r.set_cost("a", -1.0)
    with pytest.raises(ValueError):
        r.set_budget("a", -1.0)
    with pytest.raises(ValueError):
        r.spend("a", -1.0)
    with pytest.raises(ValueError):
        r.authorize("a", -1.0)
    s = r.stats()
    assert s["total_spent"] == 0 and s["exhausted"] == 0
