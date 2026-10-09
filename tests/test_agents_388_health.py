"""Slice 388 — agent health routing."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.contract import AgentContract
from hugrgate.agents.health import HealthRouter
from hugrgate.agents.registry import AgentRegistry
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentNotFound


def _router(**kw):
    kw.setdefault("alpha", 0.5)
    return HealthRouter(**kw)


def test_ewma_converges():
    r = _router()
    assert r.score("new") == 0.5  # neutral unknown
    r.report("a", True)
    assert r.score("a") == pytest.approx(0.75)  # .5*.5 + .5*1
    r.report("a", False)
    assert r.score("a") == pytest.approx(0.375)
    snap = r.snapshot("a")
    assert snap.samples == 2
    assert snap.error_rate == pytest.approx(0.5)
    assert snap.avg_latency_ms == 0.0


def test_latency_tracked_separately():
    r = _router()
    r.report("a", True, latency_ms=100.0)
    r.report("a", True, latency_ms=200.0)
    snap = r.snapshot("a")
    assert snap.avg_latency_ms == pytest.approx(150.0)
    assert snap.score == pytest.approx(0.875)  # slow but correct: healthy


def test_pick_healthiest_with_tie_break():
    r = _router()
    r.report("b", True)
    r.report("a", True)
    assert r.score("a") == r.score("b")
    assert r.pick(["b", "a"]) == "a"  # tie -> agent id order
    r.report("a", False)
    r.report("a", False)
    assert r.pick(["b", "a"]) == "b"


def test_pick_min_score_and_empty():
    r = _router()
    r.report("sick", False)
    r.report("sick", False)
    with pytest.raises(AgentNotFound) as ei:
        r.pick(["sick"], min_score=0.5)
    assert ei.value.code == "agent_not_found"
    with pytest.raises(ValueError):
        r.pick([])


def test_degraded_and_edge_triggered_signal():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("health.degraded", seen.append)
    r = HealthRouter(alpha=0.5, degrade_threshold=0.5, bus=bus)
    assert not r.degraded("a")
    r.report("a", False)  # 0.25 < 0.5 -> crosses
    assert r.degraded("a")
    assert len(seen) == 1
    assert seen[0].payload["agent_id"] == "a"
    r.report("a", False)  # still degraded: no second signal
    assert len(seen) == 1
    r.report("a", True)
    r.report("a", True)
    r.report("a", True)
    assert not r.degraded("a")  # recovered above threshold


def test_sync_registry():
    reg = AgentRegistry()
    reg.register(AgentContract(agent_id="a1"))
    reg.register(AgentContract(agent_id="a2"))
    r = _router()
    r.report("a1", False)
    r.report("a1", False)
    r.report("a2", True)
    out = r.sync_registry(reg)
    assert out == {"a1": False, "a2": True}
    assert [e.agent_id for e in
            reg.find_by_capability("x")] == []  # no such cap; sanity
    # a1 drops out of healthy_only lookups via its contract caps:
    reg2 = AgentRegistry()
    reg2.register(AgentContract(agent_id="h", capabilities=("c",)))
    r2 = _router()
    r2.report("h", False)
    r2.report("h", False)
    r2.sync_registry(reg2)
    assert reg2.find_by_capability("c") == ()
    assert len(reg2.find_by_capability("c", healthy_only=False)) == 1


def test_validation_and_stats():
    with pytest.raises(ValueError):
        HealthRouter(alpha=0.0)
    with pytest.raises(ValueError):
        HealthRouter(degrade_threshold=2.0)
    r = _router()
    with pytest.raises(ValueError):
        r.report("", True)
    r.report("a", True)
    assert r.stats() == {"agents": 1, "degraded": 0}
