"""Agent Nervous System (Campaign XVI) — agent escalation policy.

Slice 384.  When an agent cannot complete its ticket — low
confidence, policy conflict, repeated failure — the ticket must
move *up*, not spin.  :class:`EscalationPolicy` owns the ladder:

``agent → supervisor → human → terminal``

- one step per call (or an explicit higher target — never
  downward, never skipping without a reason);
- per-ticket escalation depth capped by the agent's contract
  ``max_escalation_depth`` (376) — depth beyond the contract is
  :class:`AgentEscalationFailed`, not a silent climb;
- per-ticket cooldown: re-escalation inside ``cooldown_s`` is
  refused so a flapping agent cannot strobe the levels;
- ``terminal`` is the end of the line — escalating from terminal
  fails loudly instead of wrapping around.

Every escalation publishes ``agent.escalated`` on the bus (trace
id preserved) so triage's urgent rules (377), notification gating
(382), and the provenance graph (396) all see it.  The full
per-ticket history is queryable for replay (397).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.agents.bus import EventBus
from hugrgate.agents.contract import AgentContract
from hugrgate.agents.types import AgentSignal, AgentTicket
from hugrgate.errors import AgentEscalationFailed

__all__ = [
    "ESCALATION_LEVELS",
    "Escalation",
    "EscalationPolicy",
]

#: The escalation ladder, bottom to top.
ESCALATION_LEVELS: tuple[str, ...] = (
    "agent", "supervisor", "human", "terminal",
)


@dataclass(frozen=True)
class Escalation:
    """One rung climbed."""

    ticket_id: str
    from_level: str
    to_level: str
    reason: str
    depth: int
    at: float = 0.0


@dataclass
class EscalationPolicy:
    """Owns the escalation ladder for tickets."""

    def __init__(
        self,
        cooldown_s: float = 30.0,
        bus: EventBus | None = None,
        contracts: dict[str, AgentContract] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if cooldown_s < 0:
            raise ValueError("cooldown_s must be >= 0")
        self.cooldown_s = cooldown_s
        self._bus = bus
        self._contracts = contracts or {}
        self._clock = clock or time.monotonic
        self._levels: dict[str, str] = {}  # ticket_id -> level
        self._history: dict[str, list[Escalation]] = {}
        self._last_at: dict[str, float] = {}

    def level_of(self, ticket_id: str) -> str:
        """Current ladder level of ``ticket_id`` (default ``"agent"``)."""
        return self._levels.get(ticket_id, "agent")

    def history(self, ticket_id: str) -> tuple[Escalation, ...]:
        """Escalation history of ``ticket_id``, oldest first."""
        return tuple(self._history.get(ticket_id, ()))

    def escalate(
        self,
        ticket: AgentTicket,
        *,
        reason: str,
        to_level: str = "",
    ) -> Escalation:
        """Move ``ticket`` one rung up (or to ``to_level``).

        Raises :class:`AgentEscalationFailed` when the ladder is
        exhausted, the contract depth cap is hit, or cooldown is
        still active.
        """
        if not reason or not reason.strip():
            raise ValueError("reason must be non-empty")
        current = self.level_of(ticket.ticket_id)
        target = to_level or ESCALATION_LEVELS[
            min(ESCALATION_LEVELS.index(current) + 1, len(ESCALATION_LEVELS) - 1)
        ]
        if target not in ESCALATION_LEVELS:
            raise AgentEscalationFailed(
                f"unknown escalation level {to_level!r}",
                ticket_id=ticket.ticket_id,
            )
        if ESCALATION_LEVELS.index(target) <= ESCALATION_LEVELS.index(current):
            raise AgentEscalationFailed(
                f"cannot escalate {current!r} to {target!r}: not upward",
                ticket_id=ticket.ticket_id,
            )
        contract = self._contracts.get(ticket.agent_id)
        max_depth = (
            contract.max_escalation_depth if contract is not None else 3
        )
        depth = len(self._history.get(ticket.ticket_id, ())) + 1
        if depth > max_depth:
            raise AgentEscalationFailed(
                f"ticket {ticket.ticket_id!r} exceeded escalation depth "
                f"{max_depth}",
                ticket_id=ticket.ticket_id,
                max_depth=max_depth,
            )
        now = self._clock()
        last = self._last_at.get(ticket.ticket_id)
        if last is not None and now - last < self.cooldown_s:
            raise AgentEscalationFailed(
                f"ticket {ticket.ticket_id!r} escalated too recently "
                f"({now - last:.1f}s < {self.cooldown_s}s cooldown)",
                ticket_id=ticket.ticket_id,
                cooldown_s=self.cooldown_s,
            )
        escalation = Escalation(
            ticket_id=ticket.ticket_id,
            from_level=current,
            to_level=target,
            reason=reason,
            depth=depth,
            at=now,
        )
        self._levels[ticket.ticket_id] = target
        self._history.setdefault(ticket.ticket_id, []).append(escalation)
        self._last_at[ticket.ticket_id] = now
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic="agent.escalated",
                payload={
                    "ticket_id": ticket.ticket_id,
                    "agent_id": ticket.agent_id,
                    "from": current,
                    "to": target,
                    "depth": depth,
                    "reason": reason[:200],
                },
                priority="high",
                trace_id=ticket.trace_id,
                source="escalation",
            ))
        return escalation

    def stats(self) -> dict[str, Any]:
        """Ladder counters."""
        levels: dict[str, int] = {lvl: 0 for lvl in ESCALATION_LEVELS}
        for lvl in self._levels.values():
            levels[lvl] += 1
        return {
            "tickets": len(self._levels),
            "escalations": sum(len(h) for h in self._history.values()),
            "by_level": levels,
        }
