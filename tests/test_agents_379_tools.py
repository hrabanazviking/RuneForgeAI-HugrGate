"""Slice 379 — tool routing."""

from __future__ import annotations

import pytest

from hugrgate.agents.contract import AgentContract
from hugrgate.agents.tools import ToolGrant, ToolPolicy, ToolRouter
from hugrgate.errors import AgentBudgetExhausted, AgentContractViolation


def _router() -> ToolRouter:
    contracts = {
        "a1": AgentContract(agent_id="a1", tools=("search", "calc")),
    }
    r = ToolRouter(contracts=contracts)
    r.register_policy(ToolPolicy(
        agent_id="a1",
        allowed_tools=frozenset({"search", "calc", "shell", "browser"}),
        denied_tools=frozenset({"shell"}),
        max_calls_per_ticket=2,
        arg_schemas={"search": {"query": "str", "limit": "int"}},
    ))
    return r


def test_authorize_grants_and_records():
    r = _router()
    g = r.authorize("a1", "search", {"query": "x", "limit": 3}, "t1")
    assert isinstance(g, ToolGrant)
    assert g.agent_id == "a1" and g.tool == "search" and g.ticket_id == "t1"
    assert r.calls_used("a1", "t1") == 1
    r.record_result(g.call_id, True, latency_ms=12.0)
    stats = r.tool_stats("search")
    assert stats["calls"] == 1 and stats["failures"] == 0
    assert stats["mean_latency_ms"] == 12.0
    assert stats["failure_rate"] == 0.0
    r.record_result(r.authorize("a1", "calc", {}, "t1").call_id, False)
    assert r.tool_stats("calc")["failure_rate"] == 1.0


def test_deny_wins_over_allow():
    r = _router()
    with pytest.raises(AgentContractViolation) as ei:
        r.authorize("a1", "shell", {}, "t1")
    assert ei.value.details["denied"] is True


def test_tool_missing_from_contract_rejected():
    r = _router()  # contract for a1 allows only search/calc
    with pytest.raises(AgentContractViolation) as ei:
        r.authorize("a1", "browser", {}, "t1")
    # allowed by policy but not by contract -> rejected
    assert "contract" in str(ei.value)


def test_no_policy_registered_rejected():
    r = _router()
    with pytest.raises(AgentContractViolation) as ei:
        r.authorize("ghost", "search", {}, "t1")
    assert ei.value.code == "agent_contract_violation"


def test_bad_args_rejected_with_violations():
    r = _router()
    with pytest.raises(AgentContractViolation) as ei:
        r.authorize("a1", "search", {"query": "x"}, "t1")
    assert any("missing field 'limit'" in v
               for v in ei.value.details["violations"])
    with pytest.raises(AgentContractViolation):
        r.authorize("a1", "search", {"query": "x", "limit": True}, "t1")


def test_per_ticket_call_budget():
    r = _router()
    r.authorize("a1", "calc", {}, "t1")
    r.authorize("a1", "calc", {}, "t1")
    with pytest.raises(AgentBudgetExhausted) as ei:
        r.authorize("a1", "calc", {}, "t1")
    assert ei.value.code == "agent_budget_exhausted"
    assert ei.value.details["limit"] == 2
    # Budget is per ticket: a fresh ticket is unaffected.
    r.authorize("a1", "calc", {}, "t2")


def test_record_result_unknown_call_id():
    r = _router()
    with pytest.raises(ValueError):
        r.record_result("call-999999", True)


def test_policy_validation_and_lookup():
    r = ToolRouter()
    with pytest.raises(ValueError):
        ToolPolicy(agent_id="", allowed_tools=frozenset({"x"}))
    with pytest.raises(ValueError):
        ToolPolicy(agent_id="a", max_calls_per_ticket=0)
    assert r.policy_for("nobody") is None
    p = ToolPolicy(agent_id="a", allowed_tools=frozenset({"x"}))
    r.register_policy(p)
    assert r.policy_for("a") is p
    assert r.tool_stats("never-used")["calls"] == 0
