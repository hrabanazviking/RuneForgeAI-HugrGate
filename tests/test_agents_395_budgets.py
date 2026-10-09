"""Slice 395 — decision budgets per agent."""

from __future__ import annotations

import pytest

from hugrgate.agents.budgets import BudgetLedger, DecisionBudget
from hugrgate.errors import AgentBudgetExhausted


def _ledger():
    led = BudgetLedger()
    led.allocate("a", DecisionBudget(decisions=2, tokens=100,
                                    latency_ms=1000.0))
    return led


def test_consume_and_remaining():
    led = _ledger()
    rem = led.consume("a", decisions=1, tokens=30, latency_ms=100.0)
    assert (rem.decisions, rem.tokens) == (1, 70)
    assert rem.latency_ms == pytest.approx(900.0)
    s = led.stats()
    assert s["consumptions"] == 1 and s["agents"] == 1


def test_each_dimension_exhausts():
    led = _ledger()
    led.consume("a", decisions=2)
    with pytest.raises(AgentBudgetExhausted) as ei:
        led.consume("a", decisions=1)
    assert ei.value.details["dimension"] == "decisions"
    assert ei.value.recoverable is True

    l2 = BudgetLedger()
    l2.allocate("b", DecisionBudget(tokens=10))
    l2.consume("b", decisions=0, tokens=10)
    with pytest.raises(AgentBudgetExhausted) as ei:
        l2.consume("b", decisions=0, tokens=1)
    assert ei.value.details["dimension"] == "tokens"

    l3 = BudgetLedger()
    l3.allocate("c", DecisionBudget(latency_ms=5.0))
    with pytest.raises(AgentBudgetExhausted) as ei:
        l3.consume("c", decisions=0, latency_ms=5.1)
    assert ei.value.details["dimension"] == "latency_ms"
    assert l3.stats()["exhaustions"] == 1


def test_exact_limit_allowed():
    led = _ledger()
    led.consume("a", decisions=2, tokens=100, latency_ms=1000.0)
    rem = led.remaining("a")
    assert (rem.decisions, rem.tokens, rem.latency_ms) == (0, 0, 0.0)


def test_unallocated_agent_rejected():
    led = BudgetLedger()
    with pytest.raises(AgentBudgetExhausted) as ei:
        led.consume("ghost", decisions=1)
    assert ei.value.code == "agent_budget_exhausted"
    assert led.remaining("ghost").decisions == 0
    assert led.reset("ghost") is False


def test_reset_and_top_up():
    led = _ledger()
    led.consume("a", decisions=2)
    with pytest.raises(AgentBudgetExhausted):
        led.consume("a", decisions=1)
    assert led.reset("a") is True
    led.consume("a", decisions=1)  # new window
    led.top_up("a", DecisionBudget(decisions=5, tokens=0, latency_ms=0.0))
    rem = led.remaining("a")
    assert rem.decisions == 2 + 5 - 1
    with pytest.raises(ValueError):
        led.top_up("ghost", DecisionBudget())


def test_validation():
    led = BudgetLedger()
    with pytest.raises(ValueError):
        led.allocate("", DecisionBudget())
    with pytest.raises(ValueError):
        DecisionBudget(decisions=-1)
    with pytest.raises(ValueError):
        DecisionBudget(tokens=-1)
    with pytest.raises(ValueError):
        DecisionBudget(latency_ms=-1.0)
    led.allocate("a", DecisionBudget())
    with pytest.raises(ValueError):
        led.consume("a", decisions=-1)
