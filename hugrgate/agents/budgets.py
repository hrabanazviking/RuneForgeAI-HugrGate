"""Agent Nervous System (Campaign XVI) — decision budgets per agent.

Slice 395.  Three budget systems, three jobs — no overlap:

- cost router (389): *routing-time* wallets — "can we afford to
  send this ticket there";
- runaway guard (394): *per-ticket* ceilings — "this ticket has
  gone too far";
- this ledger: *per-agent* execution budgets across tickets —
  "this agent has done enough this window".

:class:`BudgetLedger` allocates each agent a :class:`DecisionBudget`
(decisions, tokens, latency_ms); :meth:`consume` charges usage
and raises :class:`AgentBudgetExhausted` naming the exhausted
dimension with limit/used in details.  Exhaustion is recoverable:
:meth:`reset` opens a new window, :meth:`top_up` adds headroom —
a supervisor or operator decides, never the agent itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hugrgate.errors import AgentBudgetExhausted

__all__ = [
    "BudgetLedger",
    "DecisionBudget",
]

#: Budget dimensions, in check order.
DIMENSIONS: tuple[str, ...] = ("decisions", "tokens", "latency_ms")


@dataclass(frozen=True)
class DecisionBudget:
    """One agent's budget (or remaining budget)."""

    decisions: int = 1000
    tokens: int = 1_000_000
    latency_ms: float = 3_600_000.0

    def __post_init__(self) -> None:
        if self.decisions < 0:
            raise ValueError("decisions must be >= 0")
        if self.tokens < 0:
            raise ValueError("tokens must be >= 0")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")


class BudgetLedger:
    """Per-agent execution budgets with exhaustion errors."""

    def __init__(self) -> None:
        self._budgets: dict[str, DecisionBudget] = {}
        self._used: dict[str, dict[str, float]] = {}
        self._stats = {"consumptions": 0, "exhaustions": 0}

    def allocate(self, agent_id: str, budget: DecisionBudget) -> None:
        """Set (or replace) an agent's budget; usage resets."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        self._budgets[agent_id] = budget
        self._used[agent_id] = {"decisions": 0.0, "tokens": 0.0,
                                "latency_ms": 0.0}

    def top_up(self, agent_id: str, extra: DecisionBudget) -> None:
        """Add headroom to an existing budget."""
        current = self._budgets.get(agent_id)
        if current is None:
            raise ValueError(f"no budget allocated for {agent_id!r}")
        self._budgets[agent_id] = DecisionBudget(
            decisions=current.decisions + extra.decisions,
            tokens=current.tokens + extra.tokens,
            latency_ms=current.latency_ms + extra.latency_ms,
        )

    def reset(self, agent_id: str) -> bool:
        """Open a new window (zero usage); True when allocated."""
        if agent_id not in self._budgets:
            return False
        self._used[agent_id] = {"decisions": 0.0, "tokens": 0.0,
                                "latency_ms": 0.0}
        return True

    def remaining(self, agent_id: str) -> DecisionBudget:
        """Unspent budget (zeros when unallocated)."""
        budget = self._budgets.get(agent_id)
        if budget is None:
            return DecisionBudget(decisions=0, tokens=0, latency_ms=0.0)
        used = self._used[agent_id]
        return DecisionBudget(
            decisions=max(0, budget.decisions - int(used["decisions"])),
            tokens=max(0, budget.tokens - int(used["tokens"])),
            latency_ms=max(0.0, budget.latency_ms - used["latency_ms"]),
        )

    def consume(
        self,
        agent_id: str,
        *,
        decisions: int = 1,
        tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> DecisionBudget:
        """Charge usage; raises :class:`AgentBudgetExhausted` when dry.

        Returns the remaining budget after the charge.
        """
        if decisions < 0 or tokens < 0 or latency_ms < 0:
            raise ValueError("consumption must be >= 0")
        budget = self._budgets.get(agent_id)
        if budget is None:
            raise AgentBudgetExhausted(
                f"agent {agent_id!r} has no budget allocated",
                agent_id=agent_id,
            )
        used = self._used[agent_id]
        charges = {"decisions": float(decisions), "tokens": float(tokens),
                   "latency_ms": latency_ms}
        limits = {"decisions": float(budget.decisions),
                  "tokens": float(budget.tokens),
                  "latency_ms": budget.latency_ms}
        for dim in DIMENSIONS:
            if used[dim] + charges[dim] > limits[dim]:
                self._stats["exhaustions"] += 1
                raise AgentBudgetExhausted(
                    f"agent {agent_id!r} exhausted {dim} budget: "
                    f"{used[dim] + charges[dim]:g} > {limits[dim]:g}",
                    agent_id=agent_id,
                    dimension=dim,
                    used=used[dim] + charges[dim],
                    limit=limits[dim],
                )
        for dim in DIMENSIONS:
            used[dim] += charges[dim]
        self._stats["consumptions"] += 1
        return self.remaining(agent_id)

    def stats(self) -> dict[str, Any]:
        """Ledger counters (copy)."""
        return {
            "agents": len(self._budgets),
            "consumptions": self._stats["consumptions"],
            "exhaustions": self._stats["exhaustions"],
        }
