"""Slice 384 — agent escalation policy."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus
from hugrgate.agents.contract import AgentContract
from hugrgate.agents.escalation import ESCALATION_LEVELS, EscalationPolicy
from hugrgate.agents.types import AgentSignal, AgentTicket
from hugrgate.errors import AgentEscalationFailed


def _ticket(tid="t1", agent="a1"):
    return AgentTicket(ticket_id=tid, agent_id=agent, intent="i")


def _policy(**kw):
    clock = [1000.0]
    kw.setdefault("clock", lambda: clock[0])
    p = EscalationPolicy(**kw)
    return p, clock


def test_ladder_climbs_one_rung():
    p, clock = _policy()
    t = _ticket()
    assert p.level_of(t.ticket_id) == "agent"
    e1 = p.escalate(t, reason="low confidence")
    assert (e1.from_level, e1.to_level, e1.depth) == ("agent", "supervisor", 1)
    clock[0] += 31.0
    e2 = p.escalate(t, reason="still stuck")
    assert (e2.from_level, e2.to_level) == ("supervisor", "human")
    assert [e.to_level for e in p.history(t.ticket_id)] == ["supervisor", "human"]
    s = p.stats()
    assert s["escalations"] == 2 and s["by_level"]["human"] == 1


def test_explicit_target_and_no_downward():
    p, _ = _policy()
    t = _ticket()
    e = p.escalate(t, reason="urgent", to_level="human")
    assert e.to_level == "human"
    with pytest.raises(AgentEscalationFailed):
        p.escalate(t, reason="back down", to_level="agent")
    with pytest.raises(AgentEscalationFailed):
        p.escalate(t, reason="bad level", to_level="ceo")


def test_terminal_is_the_end():
    p, clock = _policy()
    t = _ticket()
    p.escalate(t, reason="r1", to_level="terminal")
    assert p.level_of(t.ticket_id) == "terminal"
    clock[0] += 31.0
    with pytest.raises(AgentEscalationFailed):
        p.escalate(t, reason="r2")


def test_contract_depth_cap():
    contracts = {"a1": AgentContract(agent_id="a1", max_escalation_depth=1)}
    p, clock = _policy(contracts=contracts)
    t = _ticket()
    p.escalate(t, reason="r1")
    clock[0] += 31.0
    with pytest.raises(AgentEscalationFailed) as ei:
        p.escalate(t, reason="r2")
    assert ei.value.details["max_depth"] == 1
    assert ei.value.code == "agent_escalation_failed"


def test_cooldown_refuses_flapping():
    p, clock = _policy(cooldown_s=30.0)
    t = _ticket()
    p.escalate(t, reason="r1")
    with pytest.raises(AgentEscalationFailed) as ei:
        p.escalate(t, reason="r2")
    assert "cooldown" in str(ei.value).lower()
    clock[0] += 30.0
    p.escalate(t, reason="r2")  # exactly at cooldown: allowed


def test_reason_required_and_bus_signal():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("agent.escalated", seen.append)
    p, _ = _policy(bus=bus)
    t = _ticket()
    with pytest.raises(ValueError):
        p.escalate(t, reason="  ")
    p.escalate(t, reason="needs eyes")
    assert len(seen) == 1
    assert seen[0].payload["to"] == "supervisor"
    assert seen[0].trace_id == t.trace_id
    assert seen[0].priority == "high"


def test_ladder_constant():
    assert ESCALATION_LEVELS == ("agent", "supervisor", "human", "terminal")
