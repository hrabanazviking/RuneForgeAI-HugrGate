"""Slice 394 — runaway escalation guard."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.runaway import RunawayGuard, RunawayLimits
from hugrgate.agents.types import AgentSignal, AgentTicket
from hugrgate.errors import AgentRunaway


def _guard(**kw):
    kw.setdefault("limits", RunawayLimits(
        max_escalations_per_ticket=2, max_steps_per_ticket=10,
        max_tokens_per_ticket=100))
    return RunawayGuard(**kw)


def _ticket(tid="t1"):
    return AgentTicket(ticket_id=tid, agent_id="a", intent="i")


def test_escalation_budget():
    g = _guard()
    t = _ticket()
    assert g.check_escalation(t).escalations == 1
    assert g.check_escalation(t).escalations == 2
    with pytest.raises(AgentRunaway) as ei:
        g.check_escalation(t)
    assert ei.value.code == "agent_runaway"
    assert ei.value.recoverable is False
    assert ei.value.details["breach"] == "escalations"
    assert g.stats()["breaches"] == 1


def test_step_and_token_budgets():
    g = _guard()
    t = _ticket()
    g.consume(t, steps=9, tokens=50)
    u = g.usage(t.ticket_id)
    assert (u.steps, u.tokens) == (9, 50)
    with pytest.raises(AgentRunaway) as ei:
        g.consume(t, steps=2)
    assert ei.value.details["breach"] == "steps"
    with pytest.raises(AgentRunaway) as ei:
        g.consume(_ticket("t2"), tokens=101)
    assert ei.value.details["breach"] == "tokens"
    with pytest.raises(ValueError):
        g.consume(t, steps=-1)


def test_kill_switch_halts_everything():
    g = _guard()
    g.trip_kill_switch("operator panic")
    assert g.kill_switch_tripped
    with pytest.raises(AgentRunaway) as ei:
        g.check_escalation(_ticket("new"))
    assert "kill switch" in str(ei.value)
    with pytest.raises(AgentRunaway):
        g.consume(_ticket("new2"), steps=1)
    g.reset_kill_switch()
    assert not g.kill_switch_tripped
    assert g.check_escalation(_ticket("new")).escalations == 1
    with pytest.raises(ValueError):
        g.trip_kill_switch("  ")


def test_breach_bus_signal():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("agent.runaway", seen.append)
    g = _guard(bus=bus)
    t = _ticket()
    g.check_escalation(t)
    g.check_escalation(t)
    with pytest.raises(AgentRunaway):
        g.check_escalation(t)
    assert len(seen) == 1
    assert seen[0].priority == "critical"
    assert seen[0].payload["breach"] == "escalations"
    assert seen[0].trace_id == t.trace_id
    g.trip_kill_switch("test")
    assert seen[-1].payload["kill_switch"] is True


def test_usage_reset_and_limits_validation():
    g = _guard()
    assert g.usage("ghost").steps == 0
    g.consume(_ticket("t1"), steps=1)
    assert g.reset("t1") is True
    assert g.reset("t1") is False
    assert g.usage("t1").steps == 0
    with pytest.raises(ValueError):
        RunawayLimits(max_steps_per_ticket=0)
    s = g.stats()
    assert s["tickets"] == 1 and s["kills"] == 0
