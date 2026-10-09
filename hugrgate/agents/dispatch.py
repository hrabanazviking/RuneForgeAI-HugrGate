"""Agent Nervous System (Campaign XVI) — multi-agent dispatch.

Slice 386.  Hard problems deserve more than one mind.
:class:`MultiAgentDispatch` fans one ticket out to several agents
and reconciles their answers with three strategies:

- ``"parallel"`` — every agent runs; all results collected
  (reconciliation belongs to fusion, slice 391);
- ``"race"`` — the successful call with the lowest latency wins;
- ``"quorum"`` — the first ``quorum`` successes win; fewer than
  ``quorum`` successes is a failed dispatch.

Execution is **sequential and deterministic** by design: the
dispatcher is the unit under replay (397), and replay demands
repeatable order.  Concurrency is a deployment choice for the
service layer, not the nervous system.  Latencies are measured
per call so ``"race"`` still selects the genuinely fastest agent.

Each call is wrapped: exceptions become failed
:class:`AgentCallResult`s (never propagate — one bad agent must
not sink the dispatch), and a ``dispatch.completed`` bus signal
carries winner, strategy, and per-agent latencies for
observability.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.bus import EventBus
from hugrgate.agents.types import AgentSignal, AgentTicket

__all__ = [
    "STRATEGIES",
    "AgentCallResult",
    "DispatchResult",
    "MultiAgentDispatch",
]

#: Allowed dispatch strategies.
STRATEGIES: tuple[str, ...] = ("parallel", "race", "quorum")

#: Agent call signature: ticket -> (output, confidence).
AgentFn = Callable[[AgentTicket], tuple[Any, float]]


@dataclass(frozen=True)
class AgentCallResult:
    """Outcome of one agent's call."""

    agent_id: str
    ok: bool
    output: Any = None
    confidence: float = 0.0
    latency_ms: float = 0.0
    error: str = ""


@dataclass(frozen=True)
class DispatchResult:
    """Reconciled outcome of a fan-out."""

    strategy: str
    ok: bool
    results: dict[str, AgentCallResult] = field(default_factory=dict)
    winner: str = ""
    reason: str = ""


class MultiAgentDispatch:
    """Deterministic fan-out dispatcher over agent callables."""

    def __init__(
        self,
        bus: EventBus | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._bus = bus
        self._clock = clock or time.monotonic
        self._stats: dict[str, Any] = {
            "dispatches": 0,
            "by_strategy": {s: 0 for s in STRATEGIES},
        }

    def dispatch(
        self,
        ticket: AgentTicket,
        calls: dict[str, AgentFn],
        *,
        strategy: str = "parallel",
        quorum: int = 2,
    ) -> DispatchResult:
        """Fan out ``ticket`` to ``calls`` and reconcile."""
        if strategy not in STRATEGIES:
            raise ValueError(f"strategy must be one of {STRATEGIES}")
        if not calls:
            raise ValueError("calls must not be empty")
        if strategy == "quorum" and quorum > len(calls):
            raise ValueError("quorum cannot exceed the number of agents")
        if quorum < 1:
            raise ValueError("quorum must be >= 1")

        results: dict[str, AgentCallResult] = {}
        for agent_id, fn in calls.items():
            start = self._clock()
            try:
                output, confidence = fn(ticket)
                latency_ms = (self._clock() - start) * 1000.0
                if not 0.0 <= confidence <= 1.0:
                    raise ValueError(
                        f"confidence {confidence!r} out of [0, 1]")
                results[agent_id] = AgentCallResult(
                    agent_id=agent_id, ok=True, output=output,
                    confidence=confidence, latency_ms=max(0.0, latency_ms),
                )
            except Exception as exc:  # noqa: BLE001 - isolated per agent
                latency_ms = (self._clock() - start) * 1000.0
                results[agent_id] = AgentCallResult(
                    agent_id=agent_id, ok=False,
                    latency_ms=max(0.0, latency_ms), error=str(exc),
                )

        result = self._reconcile(strategy, quorum, results)
        self._stats["dispatches"] += 1
        self._stats["by_strategy"][strategy] += 1
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic="dispatch.completed",
                payload={
                    "ticket_id": ticket.ticket_id,
                    "strategy": strategy,
                    "ok": result.ok,
                    "winner": result.winner,
                    "agents": sorted(results),
                    "failures": sum(1 for r in results.values() if not r.ok),
                },
                priority="normal",
                trace_id=ticket.trace_id,
                source="dispatch",
            ))
        return result

    @staticmethod
    def _reconcile(
        strategy: str, quorum: int, results: dict[str, AgentCallResult]
    ) -> DispatchResult:
        ok = {aid: r for aid, r in results.items() if r.ok}
        if strategy == "parallel":
            return DispatchResult(
                strategy=strategy, ok=bool(ok), results=results,
                winner="",
                reason=(f"{len(ok)}/{len(results)} succeeded"
                        if ok else "all agents failed"),
            )
        if strategy == "race":
            if not ok:
                return DispatchResult(strategy=strategy, ok=False,
                                      results=results,
                                      reason="all agents failed")
            winner = min(ok, key=lambda aid: ok[aid].latency_ms)
            return DispatchResult(strategy=strategy, ok=True,
                                  results=results, winner=winner,
                                  reason=f"fastest success: {winner}")
        # quorum
        if len(ok) >= quorum:
            winners = sorted(ok)[:quorum]
            return DispatchResult(strategy=strategy, ok=True,
                                  results=results, winner=winners[0],
                                  reason=f"quorum {len(ok)}/{quorum} met")
        return DispatchResult(
            strategy=strategy, ok=False, results=results,
            reason=f"quorum missed: {len(ok)}/{quorum} successes",
        )

    def stats(self) -> dict[str, Any]:
        """Dispatcher counters (copy)."""
        import copy

        return copy.deepcopy(self._stats)
