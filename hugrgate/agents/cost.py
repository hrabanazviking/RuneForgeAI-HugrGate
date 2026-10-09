"""Agent Nervous System (Campaign XVI) — agent cost routing.

Slice 389.  Health (388) answers "who deserves traffic"; cost
answers "who can we afford".  :class:`CostRouter` keeps
per-agent cost ledgers:

- ``set_cost(agent_id, cost_per_decision)`` — the price tag;
- ``set_budget(agent_id, budget)`` — the wallet (``None`` =
  unbounded);
- ``spend(agent_id, amount)`` — records actuals; crossing the
  budget fires one edge-triggered ``cost.budget_exhausted`` bus
  signal;
- ``authorize(agent_id, estimated_cost)`` — ``True`` when the
  estimate fits the remaining budget (routing predicate);
- ``pick_cheapest(candidates, max_cost=...)`` — cheapest known
  agent within an optional per-decision cap; unknown costs sort
  as +infinity (never preferred over a priced agent), and no
  affordable candidate raises :class:`AgentNotFound`.

Costs are abstract units — the same unit the contract
``max_cost`` SLO (376) speaks.  Budgets here are *routing*
budgets; the hard per-agent decision/token/latency budgets of
slice 395 enforce at execution time.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.agents.bus import EventBus
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import AgentNotFound

__all__ = [
    "CostLedger",
    "CostRouter",
]


@dataclass(frozen=True)
class CostLedger:
    """One agent's cost position."""

    agent_id: str
    cost_per_decision: float
    budget: float | None
    spent: float
    remaining: float | None
    exhausted: bool


class CostRouter:
    """Per-agent cost ledgers with cheapest-first routing."""

    def __init__(
        self,
        bus: EventBus | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._bus = bus
        self._costs: dict[str, float] = {}
        self._budgets: dict[str, float] = {}
        self._spent: dict[str, float] = {}
        self._exhausted_flag: dict[str, bool] = {}

    def set_cost(self, agent_id: str, cost_per_decision: float) -> None:
        """Set an agent's price per decision."""
        if cost_per_decision < 0:
            raise ValueError("cost_per_decision must be >= 0")
        self._costs[agent_id] = cost_per_decision

    def set_budget(self, agent_id: str, budget: float | None) -> None:
        """Set an agent's budget (``None`` = unbounded)."""
        if budget is not None and budget < 0:
            raise ValueError("budget must be >= 0 or None")
        if budget is None:
            self._budgets.pop(agent_id, None)
        else:
            self._budgets[agent_id] = budget
        self._exhausted_flag.pop(agent_id, None)

    def spend(self, agent_id: str, amount: float) -> CostLedger:
        """Record actual spend; returns the updated ledger."""
        if amount < 0:
            raise ValueError("amount must be >= 0")
        self._spent[agent_id] = self._spent.get(agent_id, 0.0) + amount
        ledger = self.ledger(agent_id)
        if ledger.exhausted and not self._exhausted_flag.get(agent_id, False):
            self._exhausted_flag[agent_id] = True
            bus = self._bus
            if bus is not None:
                bus.publish(AgentSignal(
                    topic="cost.budget_exhausted",
                    payload={"agent_id": agent_id,
                             "spent": round(ledger.spent, 4),
                             "budget": ledger.budget},
                    priority="high",
                    source="cost",
                ))
        return ledger

    def ledger(self, agent_id: str) -> CostLedger:
        """The agent's current cost position."""
        cost = self._costs.get(agent_id, math.inf)
        budget = self._budgets.get(agent_id)
        spent = self._spent.get(agent_id, 0.0)
        remaining = None if budget is None else max(0.0, budget - spent)
        exhausted = budget is not None and spent >= budget
        return CostLedger(
            agent_id=agent_id, cost_per_decision=cost, budget=budget,
            spent=spent, remaining=remaining, exhausted=exhausted,
        )

    def authorize(self, agent_id: str, estimated_cost: float) -> bool:
        """True when ``estimated_cost`` fits the remaining budget."""
        if estimated_cost < 0:
            raise ValueError("estimated_cost must be >= 0")
        ledger = self.ledger(agent_id)
        if ledger.budget is None:
            return True
        if ledger.exhausted:
            # Hard stop: an exhausted budget blocks further decisions
            # even for zero-cost estimates.
            return False
        remaining = ledger.remaining
        assert remaining is not None  # budget set -> remaining computed
        return remaining >= estimated_cost

    def pick_cheapest(
        self,
        candidates: tuple[str, ...] | list[str],
        *,
        max_cost: float | None = None,
    ) -> str:
        """Cheapest candidate within ``max_cost`` (ties → agent id).

        Unknown costs sort as +infinity — never preferred over a
        priced agent.  Raises :class:`AgentNotFound` when nothing
        is affordable.
        """
        if not candidates:
            raise ValueError("candidates must not be empty")
        priced = [
            (self._costs.get(c, math.inf), c) for c in candidates
        ]
        if max_cost is not None:
            priced = [(p, c) for p, c in priced if p <= max_cost]
        if not priced:
            raise AgentNotFound(
                "no affordable candidate",
                candidates=list(candidates),
                max_cost=max_cost,
            )
        priced.sort(key=lambda pc: (pc[0], pc[1]))
        return priced[0][1]

    def stats(self) -> dict[str, Any]:
        """Router counters (copy)."""
        return {
            "agents": len(set(self._costs) | set(self._budgets)
                           | set(self._spent)),
            "total_spent": round(sum(self._spent.values()), 4),
            "exhausted": sum(1 for v in self._exhausted_flag.values() if v),
        }
