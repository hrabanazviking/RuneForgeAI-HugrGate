"""Agent Nervous System (Campaign XVI) — runaway escalation guard.

Slice 394.  The loop-breaker (393) catches *cycles*; the runaway
guard catches *everything else that never ends*: escalation
storms, thousand-step tickets, token hemorrhages.  It is the
last line of defense, and it is deliberately terminal — a
breach raises :class:`AgentRunaway` (not recoverable: the ticket
is dead, start a new one).

- per-ticket counters: escalations, steps, tokens;
  :meth:`check_escalation` / :meth:`consume` increment and
  enforce ``max_escalations_per_ticket`` /
  ``max_steps_per_ticket`` / ``max_tokens_per_ticket``;
- :meth:`trip_kill_switch` halts *all* tickets immediately
  (operator panic button); :meth:`reset_kill_switch` re-arms;
- every breach and kill-switch event publishes ``agent.runaway``
  (critical) on the bus with the counter values in the payload —
  triage routes it urgent, notification pages, provenance
  records the kill.

The guard composes with the loop-breaker: wire the breaker's
``agent.loop`` signal to ``check_escalation`` and cycles cost
escalation budget too.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from hugrgate.agents.bus import EventBus
from hugrgate.agents.types import AgentSignal, AgentTicket
from hugrgate.errors import AgentRunaway

__all__ = [
    "RunawayGuard",
    "RunawayLimits",
    "TicketUsage",
]


@dataclass(frozen=True)
class RunawayLimits:
    """Per-ticket ceilings."""

    max_escalations_per_ticket: int = 8
    max_steps_per_ticket: int = 256
    max_tokens_per_ticket: int = 64_000

    def __post_init__(self) -> None:
        for name in ("max_escalations_per_ticket", "max_steps_per_ticket",
                     "max_tokens_per_ticket"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")


@dataclass(frozen=True)
class TicketUsage:
    """One ticket's consumption."""

    ticket_id: str
    escalations: int
    steps: int
    tokens: int


class RunawayGuard:
    """Terminal guard against runaway tickets and kill-switch."""

    def __init__(
        self,
        limits: RunawayLimits | None = None,
        bus: EventBus | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._limits = limits or RunawayLimits()
        self._bus = bus
        self._clock = clock or time.monotonic
        self._usage: dict[str, dict[str, int]] = {}
        self._killed = False
        self._kill_reason = ""
        self._stats = {"breaches": 0, "kills": 0, "tickets": 0}

    @property
    def kill_switch_tripped(self) -> bool:
        """True while the kill switch is engaged."""
        return self._killed

    def _use(self, ticket_id: str) -> dict[str, int]:
        use = self._usage.get(ticket_id)
        if use is None:
            use = {"escalations": 0, "steps": 0, "tokens": 0}
            self._usage[ticket_id] = use
            self._stats["tickets"] += 1
        return use

    def _breach(
        self, ticket: AgentTicket, what: str, used: int, limit: int
    ) -> AgentRunaway:
        self._stats["breaches"] += 1
        use = self._usage[ticket.ticket_id]
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic="agent.runaway",
                payload={
                    "ticket_id": ticket.ticket_id,
                    "breach": what,
                    "used": used,
                    "limit": limit,
                    "escalations": use["escalations"],
                    "steps": use["steps"],
                    "tokens": use["tokens"],
                },
                priority="critical",
                trace_id=ticket.trace_id,
                source="runaway-guard",
            ))
        return AgentRunaway(
            f"ticket {ticket.ticket_id!r} breached {what}: "
            f"{used} > {limit}",
            ticket_id=ticket.ticket_id,
            breach=what,
            used=used,
            limit=limit,
        )

    def _check_kill(self, ticket: AgentTicket) -> None:
        if self._killed:
            raise AgentRunaway(
                f"kill switch tripped ({self._kill_reason}); ticket "
                f"{ticket.ticket_id!r} halted",
                ticket_id=ticket.ticket_id,
                kill_reason=self._kill_reason,
            )

    def check_escalation(self, ticket: AgentTicket) -> TicketUsage:
        """Charge one escalation; raises :class:`AgentRunaway` past limit."""
        self._check_kill(ticket)
        use = self._use(ticket.ticket_id)
        use["escalations"] += 1
        if use["escalations"] > self._limits.max_escalations_per_ticket:
            raise self._breach(
                ticket, "escalations", use["escalations"],
                self._limits.max_escalations_per_ticket)
        return TicketUsage(ticket.ticket_id, use["escalations"],
                           use["steps"], use["tokens"])

    def consume(
        self, ticket: AgentTicket, *, steps: int = 0, tokens: int = 0
    ) -> TicketUsage:
        """Charge steps/tokens; raises :class:`AgentRunaway` past limits."""
        if steps < 0 or tokens < 0:
            raise ValueError("steps and tokens must be >= 0")
        self._check_kill(ticket)
        use = self._use(ticket.ticket_id)
        use["steps"] += steps
        use["tokens"] += tokens
        if use["steps"] > self._limits.max_steps_per_ticket:
            raise self._breach(ticket, "steps", use["steps"],
                               self._limits.max_steps_per_ticket)
        if use["tokens"] > self._limits.max_tokens_per_ticket:
            raise self._breach(ticket, "tokens", use["tokens"],
                               self._limits.max_tokens_per_ticket)
        return TicketUsage(ticket.ticket_id, use["escalations"],
                           use["steps"], use["tokens"])

    def usage(self, ticket_id: str) -> TicketUsage:
        """Current consumption for ``ticket_id`` (zeros when unknown)."""
        use = self._usage.get(ticket_id,
                              {"escalations": 0, "steps": 0, "tokens": 0})
        return TicketUsage(ticket_id, use["escalations"], use["steps"],
                           use["tokens"])

    def trip_kill_switch(self, reason: str) -> None:
        """Halt all tickets immediately."""
        if not reason or not reason.strip():
            raise ValueError("reason must be non-empty")
        self._killed = True
        self._kill_reason = reason
        self._stats["kills"] += 1
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic="agent.runaway",
                payload={"kill_switch": True, "reason": reason[:200]},
                priority="critical",
                source="runaway-guard",
            ))

    def reset_kill_switch(self) -> None:
        """Re-arm after a kill."""
        self._killed = False
        self._kill_reason = ""

    def reset(self, ticket_id: str) -> bool:
        """Forget a ticket's counters; True when it existed."""
        return self._usage.pop(ticket_id, None) is not None

    def stats(self) -> dict[str, int]:
        """Guard counters (copy)."""
        return dict(self._stats)
