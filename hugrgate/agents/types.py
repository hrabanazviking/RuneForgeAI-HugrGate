"""Agent Nervous System (Campaign XVI) — shared nervous-system types.

Slice 376.  The connective tissue for agentic loops: every agent,
signal, and decision ticket in the nervous system speaks this
vocabulary.  Signals flow over :mod:`hugrgate.agents.bus`; tickets
carry budgets, trace context, and provenance through the routers,
gates, and guards built in slices 377-400.

This module is stdlib-only and dependency-free inside ``hugrgate``
so the whole campaign layer can share it without import cycles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PRIORITIES",
    "PRIORITY_RANK",
    "AgentDelivery",
    "AgentId",
    "AgentSignal",
    "AgentTicket",
    "new_trace_id",
]

#: Agent identifier type (opaque string, e.g. ``"planner-01"``).
AgentId = str

#: Allowed signal priorities, weakest to strongest.
PRIORITIES: tuple[str, ...] = ("low", "normal", "high", "critical")

#: Numeric rank for each priority (higher = more urgent).
PRIORITY_RANK: dict[str, int] = {p: i for i, p in enumerate(PRIORITIES)}

_trace_counter = 0


def new_trace_id() -> str:
    """Generate a unique trace id for correlating nervous-system activity."""
    global _trace_counter
    _trace_counter += 1
    return f"hg-trace-{_trace_counter:08d}"


@dataclass(frozen=True)
class AgentSignal:
    """One event on the nervous system.

    ``topic`` is a dotted path (``"agent.escalated"``,
    ``"memory.write.denied"``); ``payload`` carries metadata only —
    never raw user content (privacy rule inherited from the
    observability layer).  ``dedup_key`` suppresses re-delivery of the
    same logical event inside the bus dedup window.
    """

    topic: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    priority: str = "normal"
    trace_id: str = ""
    dedup_key: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if not self.topic or not self.topic.strip():
            raise ValueError("signal topic must be non-empty")
        if self.priority not in PRIORITY_RANK:
            raise ValueError(f"unknown priority {self.priority!r}")
        object.__setattr__(
            self, "trace_id", self.trace_id or new_trace_id()
        )


@dataclass(frozen=True)
class AgentDelivery:
    """Outcome of publishing one signal on the bus."""

    signal: AgentSignal
    delivered: int = 0
    suppressed: int = 0
    dropped: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentTicket:
    """A unit of agentic work moving through the nervous system.

    Tickets are created at the edge (triage / intent routing) and
    threaded through dispatch, budgets, escalation, provenance, and
    replay.  ``parent_ticket_id`` links escalations and fan-out
    children to their origin so the provenance graph stays a DAG.
    """

    ticket_id: str
    agent_id: AgentId
    intent: str
    trace_id: str = ""
    parent_ticket_id: str = ""
    max_steps: int = 32
    max_tokens: int = 8000
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ticket_id:
            raise ValueError("ticket_id must be non-empty")
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        object.__setattr__(
            self, "trace_id", self.trace_id or new_trace_id()
        )

    def child(self, ticket_id: str, agent_id: AgentId) -> AgentTicket:
        """Derive a child ticket (fan-out / escalation) linked to this one."""
        return AgentTicket(
            ticket_id=ticket_id,
            agent_id=agent_id,
            intent=self.intent,
            trace_id=self.trace_id,
            parent_ticket_id=self.ticket_id,
            max_steps=self.max_steps,
            max_tokens=self.max_tokens,
            payload=self.payload,
        )
