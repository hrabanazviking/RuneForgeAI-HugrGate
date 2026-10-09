"""Slice 376 — agent integration contract (+ shared nervous-system substrate).

Covers the ``hugrgate.agents`` shared types, the event bus, and the
agent integration contract: success, failure, and boundary behavior.
"""

from __future__ import annotations

import pytest

from hugrgate.agents import bus as bus_mod
from hugrgate.agents.bus import EventBus, matches
from hugrgate.agents.contract import (
    AgentContract,
    assert_contract,
    check_input,
    check_output,
    validate_contract,
)
from hugrgate.agents.types import AgentSignal, AgentTicket, new_trace_id
from hugrgate.errors import AgentContractViolation


def _contract(**kw):
    base = dict(
        agent_id="planner-01",
        version="1.2.0",
        capabilities=("summarize", "classify"),
        intents=("summarize.text",),
        tools=("web_search",),
        input_schema={"text": "str", "max_tokens": "int"},
        output_schema={"summary": "str", "confidence": "float"},
        max_latency_ms=2000.0,
        max_cost=0.5,
        min_confidence=0.7,
        privacy_clearance="sensitive",
        max_escalation_depth=2,
    )
    base.update(kw)
    return AgentContract(**base)


# --- shared types ------------------------------------------------------------


def test_signal_requires_topic_and_known_priority():
    with pytest.raises(ValueError):
        AgentSignal(topic="")
    with pytest.raises(ValueError):
        AgentSignal(topic="a.b", priority="urgent")
    s = AgentSignal(topic="a.b")
    assert s.priority == "normal"
    assert s.trace_id.startswith("hg-trace-")


def test_trace_ids_unique():
    assert new_trace_id() != new_trace_id()


def test_ticket_child_links_parent_and_trace():
    t = AgentTicket(ticket_id="t1", agent_id="a", intent="i")
    c = t.child("t2", "b")
    assert c.parent_ticket_id == "t1"
    assert c.trace_id == t.trace_id
    assert c.ticket_id == "t2"


def test_ticket_rejects_bad_budgets():
    with pytest.raises(ValueError):
        AgentTicket(ticket_id="t", agent_id="a", intent="i", max_steps=0)
    with pytest.raises(ValueError):
        AgentTicket(ticket_id="", agent_id="a", intent="i")


# --- event bus ---------------------------------------------------------------


def test_bus_exact_prefix_and_wildcard_patterns():
    assert matches("a.b", "a.b")
    assert matches("a.*", "a.b.c")
    assert matches("a.*", "a")
    assert matches("*", "anything.at.all")
    assert not matches("a.*", "b.c")
    assert not matches("a.b", "a.c")


def test_bus_delivers_in_priority_order():
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("evt", lambda s: seen.append("low"), priority=1)
    bus.subscribe("evt", lambda s: seen.append("high"), priority=9)
    bus.subscribe("evt", lambda s: seen.append("mid"), priority=5)
    d = bus.publish(AgentSignal(topic="evt"))
    assert d.delivered == 3
    assert seen == ["high", "mid", "low"]


def test_bus_dedup_suppresses_repeat_keys():
    clock = [1000.0]
    bus = EventBus(dedup_window_s=60.0, clock=lambda: clock[0])
    hits: list[AgentSignal] = []
    bus.subscribe("*", hits.append)
    s1 = AgentSignal(topic="evt", dedup_key="k1")
    s2 = AgentSignal(topic="evt", dedup_key="k1")
    d1 = bus.publish(s1)
    d2 = bus.publish(s2)
    assert (d1.delivered, d1.suppressed) == (1, 0)
    assert (d2.delivered, d2.suppressed) == (0, 1)
    clock[0] += 61.0
    d3 = bus.publish(AgentSignal(topic="evt", dedup_key="k1"))
    assert d3.delivered == 1
    assert bus.stats()["suppressed_dedup"] == 1


def test_bus_handler_errors_collected_not_raised():
    bus = EventBus()
    def bad(s):
        raise RuntimeError("boom")
    bus.subscribe("evt", bad)
    d = bus.publish(AgentSignal(topic="evt"))
    assert d.delivered == 0
    assert len(d.errors) == 1
    assert "boom" in d.errors[0]


def test_bus_backpressure_raise_and_drop_oldest():
    # "raise" policy: the re-entrant publish raises BackpressureError,
    # which the bus isolates as a handler error (never propagated).
    bus = EventBus(max_pending=1, backpressure="raise")
    def reenter(s):
        bus.publish(AgentSignal(topic="inner"))
    bus.subscribe("outer", reenter)
    d = bus.publish(AgentSignal(topic="outer"))
    assert any("saturated" in e for e in d.errors)
    assert bus.stats()["handler_errors"] == 1

    bus2 = EventBus(max_pending=1, backpressure="drop-oldest")
    seen2: list[str] = []
    def drop_reenter(s):
        seen2.append("outer")
        bus2.publish(AgentSignal(topic="inner"))
    bus2.subscribe("outer", drop_reenter)
    d2 = bus2.publish(AgentSignal(topic="outer"))
    assert d2.delivered == 1
    assert bus2.stats()["dropped_backpressure"] == 1
    assert seen2 == ["outer"]


def test_bus_unsubscribe_and_counts():
    bus = EventBus()
    sub = bus.subscribe("evt", lambda s: None)
    assert bus.subscription_count() == 1
    assert bus.unsubscribe(sub) is True
    assert bus.unsubscribe(sub) is False
    assert bus.subscription_count() == 0
    with pytest.raises(ValueError):
        bus.subscribe("", lambda s: None)


# --- contract ----------------------------------------------------------------


def test_valid_contract_passes():
    assert validate_contract(_contract()) == ()
    assert_contract(_contract())  # no raise


def test_contract_rejects_empty_agent_id_and_bad_version():
    v = validate_contract(_contract(agent_id="  "))
    assert any("agent_id" in x for x in v)
    v = validate_contract(_contract(version="1.2"))
    assert any("version" in x for x in v)
    v = validate_contract(_contract(version="a.b.c"))
    assert any("version" in x for x in v)


def test_contract_rejects_dup_and_empty_capabilities():
    v = validate_contract(_contract(capabilities=("a", "a")))
    assert any("duplicates" in x for x in v)
    v = validate_contract(_contract(tools=("",)))
    assert any("empty entries" in x for x in v)


def test_contract_rejects_bad_schema_types_and_slos():
    v = validate_contract(_contract(input_schema={"x": "uuid"}))
    assert any("uuid" in x for x in v)
    v = validate_contract(_contract(output_schema={"": "str"}))
    assert any("empty field names" in x for x in v)
    v = validate_contract(_contract(max_latency_ms=0))
    assert any("max_latency_ms" in x for x in v)
    v = validate_contract(_contract(max_cost=-1))
    assert any("max_cost" in x for x in v)
    v = validate_contract(_contract(min_confidence=1.5))
    assert any("min_confidence" in x for x in v)
    v = validate_contract(_contract(max_escalation_depth=-1))
    assert any("max_escalation_depth" in x for x in v)


def test_contract_rejects_unknown_privacy_clearance():
    v = validate_contract(_contract(privacy_clearance="ultra"))
    assert any("privacy_clearance" in x for x in v)
    assert validate_contract(_contract(privacy_clearance="forbidden")) == ()


def test_assert_contract_raises_with_details():
    c = _contract(version="bad", max_cost=-2)
    with pytest.raises(AgentContractViolation) as ei:
        assert_contract(c)
    assert ei.value.details["agent_id"] == "planner-01"
    assert len(ei.value.details["violations"]) == 2
    assert ei.value.code == "agent_contract_violation"
    assert ei.value.recoverable is False


def test_check_input_output_success_and_failure():
    c = _contract()
    assert check_input(c, {"text": "hi", "max_tokens": 5}) == ()
    bad = check_input(c, {"text": "hi"})
    assert any("missing field 'max_tokens'" in x for x in bad)
    bad = check_input(c, {"text": "hi", "max_tokens": "five"})
    assert any("must be int" in x for x in bad)
    assert check_output(c, {"summary": "s", "confidence": 0.9}) == ()
    bad = check_output(c, {"summary": "s", "confidence": True})
    assert any("must be float, got bool" in x for x in bad)


def test_check_payload_bool_is_not_int():
    c = _contract(input_schema={"n": "int"})
    bad = check_input(c, {"n": True})
    assert any("must be int, got bool" in x for x in bad)
    # Extra fields are allowed.
    assert check_input(c, {"n": 3, "extra": [1]}) == ()


def test_contract_capability_intent_tool_queries():
    c = _contract()
    assert c.has_capability("summarize")
    assert not c.has_capability("fly")
    assert c.handles_intent("summarize.text")
    assert c.may_use_tool("web_search")
    assert not c.may_use_tool("shell_exec")


def test_bus_module_all_contract():
    for name in bus_mod.__all__:
        assert hasattr(bus_mod, name), name
