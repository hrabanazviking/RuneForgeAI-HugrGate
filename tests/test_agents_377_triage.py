"""Slice 377 — event triage API."""

from __future__ import annotations

import pytest

from hugrgate.agents.bus import EventBus, matches
from hugrgate.agents.triage import (
    ACTIONS,
    EventTriage,
    TriageDecision,
    TriageRule,
)
from hugrgate.agents.types import AgentSignal


def test_suffix_patterns():
    assert matches("*.heartbeat", "x.heartbeat")
    assert matches("*.heartbeat", "a.b.heartbeat")
    assert not matches("*.heartbeat", "heartbeat")
    assert not matches("*.heartbeat", "x.heartbeats")


def test_rule_validation():
    with pytest.raises(ValueError):
        TriageRule(name="", topic_pattern="a", action="route")
    with pytest.raises(ValueError):
        TriageRule(name="r", topic_pattern="", action="route")
    with pytest.raises(ValueError):
        TriageRule(name="r", topic_pattern="a", action="yeet")
    with pytest.raises(ValueError):
        TriageRule(name="r", topic_pattern="a", action="route", queue="n/a")
    assert set(ACTIONS) == {"route", "drop", "defer"}


def test_first_match_wins_and_default_routes():
    t = EventTriage()
    t.add_rule(TriageRule(name="first", topic_pattern="a.*", action="drop"))
    t.add_rule(TriageRule(name="second", topic_pattern="a.b", action="route",
                          queue="urgent"))
    d = t.triage(AgentSignal(topic="a.b"))
    assert isinstance(d, TriageDecision)
    assert d.rule_name == "first" and d.dropped and d.queue == "noise"
    d2 = t.triage(AgentSignal(topic="zzz"))
    assert d2.rule_name == "default" and d2.queue == "default"
    assert not d2.dropped and not d2.deferred


def test_duplicate_rule_names_rejected():
    t = EventTriage()
    t.add_rule(TriageRule(name="r", topic_pattern="a", action="route"))
    with pytest.raises(ValueError):
        t.add_rule(TriageRule(name="r", topic_pattern="b", action="drop"))
    assert t.remove_rule("r") is True
    assert t.remove_rule("r") is False
    assert t.rules() == ()


def test_priority_boost_clamped_to_ladder():
    t = EventTriage()
    t.add_rule(TriageRule(name="up", topic_pattern="hi", action="route",
                          queue="urgent", priority_boost=10))
    d = t.triage(AgentSignal(topic="hi", priority="normal"))
    assert d.priority == "critical"
    t2 = EventTriage()
    t2.add_rule(TriageRule(name="down", topic_pattern="lo", action="route",
                           priority_boost=-10))
    d2 = t2.triage(AgentSignal(topic="lo", priority="normal"))
    assert d2.priority == "low"


def test_defer_marks_deferred_not_dropped():
    t = EventTriage()
    t.add_rule(TriageRule(name="park", topic_pattern="bulk.*", action="defer"))
    d = t.triage(AgentSignal(topic="bulk.jobs", priority="low"))
    assert d.deferred and not d.dropped
    assert d.action == "defer"


def test_stats_accumulate_per_queue_and_rule():
    t = EventTriage()
    t.add_rule(TriageRule(name="dropit", topic_pattern="n.*", action="drop"))
    t.triage(AgentSignal(topic="n.1"))
    t.triage(AgentSignal(topic="n.2"))
    t.triage(AgentSignal(topic="other"))
    s = t.stats()
    assert s["triaged"] == 3
    assert s["dropped"] == 2 and s["routed"] == 1
    assert s["by_queue"]["noise"] == 2
    assert s["by_rule"] == {"dropit": 2, "default": 1}
    # Returned stats are a copy.
    s["triaged"] = 999
    assert t.stats()["triaged"] == 3


def test_triage_publishes_decision_signal_on_bus():
    bus = EventBus()
    seen: list[AgentSignal] = []
    bus.subscribe("triage.decision", seen.append)
    t = EventTriage(bus=bus)
    src = AgentSignal(topic="agent.escalated", priority="high")
    t.triage(src)
    assert len(seen) == 1
    assert seen[0].payload["in_topic"] == "agent.escalated"
    assert seen[0].trace_id == src.trace_id  # trace continuity


def test_with_defaults_ruleset():
    t = EventTriage.with_defaults()
    assert t.triage(AgentSignal(topic="x.heartbeat")).dropped
    assert t.triage(AgentSignal(topic="telemetry.cpu")).dropped
    d = t.triage(AgentSignal(topic="agent.escalated", priority="high"))
    assert d.queue == "urgent" and d.priority == "critical"
    d = t.triage(AgentSignal(topic="agent.runaway", priority="low"))
    assert d.queue == "urgent" and d.priority == "normal"  # +1 boost
    assert t.triage(AgentSignal(topic="bulk.sync")).deferred
    assert t.triage(AgentSignal(topic="user.message")).queue == "default"
    names = [r.name for r in t.rules()]
    assert names == ["drop-heartbeats", "drop-telemetry",
                     "urgent-agent.escalated", "urgent-agent.loop",
                     "urgent-agent.runaway", "defer-bulk"]
