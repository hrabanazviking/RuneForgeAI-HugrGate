"""Slice 393 — agent loop-breaker."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.loopbreak import LoopBreaker
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentLoopDetected


def test_delegation_chain_and_return():
    lb = LoopBreaker()
    assert lb.observe("t", "planner", "worker") == ("planner", "worker")
    assert lb.observe("t", "worker", "searcher") == ("planner", "worker",
                                                     "searcher")
    assert lb.path("t") == ("planner", "worker", "searcher")
    # Returning is legitimate: pop and continue elsewhere.
    assert lb.return_to("t") == "searcher"
    assert lb.observe("t", "worker", "writer") == ("planner", "worker",
                                                   "writer")
    s = lb.stats()
    assert s["observations"] == 3 and s["returns"] == 1 and s["loops"] == 0


def test_cycle_detected():
    lb = LoopBreaker()
    lb.observe("t", "a", "b")
    lb.observe("t", "b", "c")
    with pytest.raises(AgentLoopDetected) as ei:
        lb.observe("t", "c", "a")
    assert ei.value.code == "agent_loop_detected"
    assert ei.value.recoverable is True
    assert ei.value.details["cycle"] == ["a", "b", "c", "a"]
    assert lb.stats()["loops"] == 1


def test_self_loop_and_ping_pong():
    lb = LoopBreaker()
    lb.observe("t", "a", "b")
    with pytest.raises(AgentLoopDetected):  # b -> b: self-loop
        lb.observe("t", "b", "b")
    lb2 = LoopBreaker()
    lb2.observe("t", "a", "b")
    with pytest.raises(AgentLoopDetected):  # b -> a: ping-pong
        lb2.observe("t", "b", "a")


def test_depth_cap():
    lb = LoopBreaker(max_depth=3)
    lb.observe("t", "a", "b")
    lb.observe("t", "b", "c")
    with pytest.raises(AgentLoopDetected) as ei:
        lb.observe("t", "c", "d")
    assert "exceeds max 3" in str(ei.value)
    assert lb.max_depth == 3


def test_chain_discipline():
    lb = LoopBreaker()
    lb.observe("t", "a", "b")
    with pytest.raises(ValueError):  # c is not the stack top
        lb.observe("t", "c", "d")
    with pytest.raises(ValueError):
        lb.return_to("unknown")
    with pytest.raises(ValueError):
        lb.observe("", "a", "b")
    with pytest.raises(ValueError):
        LoopBreaker(max_depth=1)


def test_tickets_isolated_and_reset():
    lb = LoopBreaker()
    lb.observe("t1", "a", "b")
    lb.observe("t2", "a", "b")
    assert lb.path("t1") == ("a", "b")
    assert lb.reset("t1") is True
    assert lb.reset("t1") is False
    assert lb.path("t1") == ()


def test_loop_bus_signal():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("agent.loop", seen.append)
    lb = LoopBreaker(bus=bus)
    lb.observe("t", "a", "b")
    with pytest.raises(AgentLoopDetected):
        lb.observe("t", "b", "a")
    assert len(seen) == 1
    assert seen[0].priority == "critical"
    assert seen[0].payload["cycle"] == ["a", "b", "a"]
