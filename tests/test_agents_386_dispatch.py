"""Slice 386 — multi-agent dispatch."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.dispatch import STRATEGIES, MultiAgentDispatch
from hugrgate.agents.types import AgentSignal, AgentTicket


def _ticket():
    return AgentTicket(ticket_id="t1", agent_id="a1", intent="i")


def _ok(output, conf=0.9):
    def fn(ticket):
        return output, conf
    return fn


def _fail(msg="boom"):
    def fn(ticket):
        raise RuntimeError(msg)
    return fn


def test_parallel_collects_all():
    d = MultiAgentDispatch()
    r = d.dispatch(_ticket(), {"a": _ok("A"), "b": _ok("B", 0.7)},
                   strategy="parallel")
    assert r.ok and r.strategy == "parallel"
    assert set(r.results) == {"a", "b"}
    assert r.results["a"].output == "A"
    assert r.results["a"].confidence == 0.9


def test_parallel_partial_failure_still_ok():
    d = MultiAgentDispatch()
    r = d.dispatch(_ticket(), {"a": _ok("A"), "b": _fail()},
                   strategy="parallel")
    assert r.ok
    assert not r.results["b"].ok
    assert "boom" in r.results["b"].error


def test_parallel_all_fail():
    d = MultiAgentDispatch()
    r = d.dispatch(_ticket(), {"a": _fail("x")}, strategy="parallel")
    assert not r.ok and r.reason == "all agents failed"


def test_race_picks_fastest_success():
    clock = [0.0]
    def slow(ticket):
        clock[0] += 0.5
        return "slow", 0.99
    def fast(ticket):
        clock[0] += 0.1
        return "fast", 0.6
    d = MultiAgentDispatch(clock=lambda: clock[0])
    r = d.dispatch(_ticket(), {"slow": slow, "fast": fast}, strategy="race")
    assert r.ok and r.winner == "fast"
    assert "fastest success" in r.reason


def test_race_skips_failures():
    d = MultiAgentDispatch()
    r = d.dispatch(_ticket(), {"bad": _fail(), "good": _ok("G")},
                   strategy="race")
    assert r.ok and r.winner == "good"


def test_quorum_met_and_missed():
    d = MultiAgentDispatch()
    r = d.dispatch(_ticket(),
                   {"a": _ok(1), "b": _ok(2), "c": _fail()},
                   strategy="quorum", quorum=2)
    assert r.ok and "quorum 2/2 met" in r.reason
    r = d.dispatch(_ticket(), {"a": _ok(1), "b": _fail()},
                   strategy="quorum", quorum=2)
    assert not r.ok and "quorum missed" in r.reason


def test_bad_confidence_is_a_failure():
    d = MultiAgentDispatch()
    def wild(ticket):
        return "x", 42.0
    r = d.dispatch(_ticket(), {"w": wild}, strategy="parallel")
    assert not r.results["w"].ok
    assert "confidence" in r.results["w"].error


def test_validation():
    d = MultiAgentDispatch()
    with pytest.raises(ValueError):
        d.dispatch(_ticket(), {"a": _ok(1)}, strategy="joust")
    with pytest.raises(ValueError):
        d.dispatch(_ticket(), {})
    with pytest.raises(ValueError):
        d.dispatch(_ticket(), {"a": _ok(1)}, strategy="quorum", quorum=5)
    with pytest.raises(ValueError):
        d.dispatch(_ticket(), {"a": _ok(1)}, strategy="quorum", quorum=0)


def test_bus_signal_and_stats():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("dispatch.completed", seen.append)
    d = MultiAgentDispatch(bus=bus)
    t = _ticket()
    d.dispatch(t, {"a": _ok(1)}, strategy="race")
    assert len(seen) == 1
    assert seen[0].payload["winner"] == "a"
    assert seen[0].trace_id == t.trace_id
    s = d.stats()
    assert s["dispatches"] == 1 and s["by_strategy"]["race"] == 1
    assert set(STRATEGIES) == {"parallel", "race", "quorum"}
