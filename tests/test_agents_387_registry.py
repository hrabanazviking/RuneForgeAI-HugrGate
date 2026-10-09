"""Slice 387 — agent capability registry."""

from __future__ import annotations

import pytest

from hugrgate.agents.contract import AgentContract
from hugrgate.agents.registry import AgentRegistry
from hugrgate.errors import AgentContractViolation, AgentNotFound


def _contract(agent_id, **kw):
    base = dict(capabilities=("summarize",), intents=("summarize.text",),
                tools=("search",))
    base.update(kw)
    return AgentContract(agent_id=agent_id, **base)


def test_register_get_unregister():
    r = AgentRegistry()
    entry = r.register(_contract("a1"), endpoint="inproc://a1")
    assert entry.agent_id == "a1"
    assert entry.endpoint == "inproc://a1"
    assert entry.healthy and entry.registered_at >= 0
    assert r.get("a1") is entry
    assert r.agent_ids() == ("a1",)
    assert len(r) == 1
    assert r.unregister("a1") is True
    assert r.unregister("a1") is False
    assert len(r) == 0


def test_get_unknown_raises():
    r = AgentRegistry()
    with pytest.raises(AgentNotFound) as ei:
        r.get("ghost")
    assert ei.value.code == "agent_not_found"
    assert ei.value.details["agent_id"] == "ghost"


def test_invalid_contract_rejected_at_register():
    r = AgentRegistry()
    with pytest.raises(AgentContractViolation):
        r.register(AgentContract(agent_id="bad", version="nope"))


def test_duplicate_register_rejected():
    r = AgentRegistry()
    r.register(_contract("a1"))
    with pytest.raises(ValueError):
        r.register(_contract("a1"))
    # Explicit unregister-then-register replaces (version change path).
    r.unregister("a1")
    r.register(_contract("a1", version="2.0.0"))
    assert r.get("a1").contract.version == "2.0.0"


def test_find_by_capability_intent_tool():
    r = AgentRegistry()
    r.register(_contract("a1"))
    r.register(_contract("b2", capabilities=("translate",),
                         intents=("translate.text",), tools=("search",)))
    assert [e.agent_id for e in r.find_by_capability("summarize")] == ["a1"]
    assert [e.agent_id for e in r.find_by_intent("translate.text")] == ["b2"]
    assert [e.agent_id for e in r.find_by_tool("search")] == ["a1", "b2"]
    assert r.find_by_capability("fly") == ()


def test_healthy_only_default():
    r = AgentRegistry()
    r.register(_contract("a1"))
    r.register(_contract("a2"))
    r.set_health("a1", False, note="crashing")
    assert r.get("a1").healthy is False
    assert r.get("a1").health_note == "crashing"
    assert [e.agent_id for e in r.find_by_capability("summarize")] == ["a2"]
    assert [e.agent_id for e in
            r.find_by_capability("summarize", healthy_only=False)] == ["a1", "a2"]
    r.set_health("a1", True)
    assert [e.agent_id for e in r.find_by_capability("summarize")] == ["a1", "a2"]
    with pytest.raises(AgentNotFound):
        r.set_health("ghost", False)
