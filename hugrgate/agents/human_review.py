"""Agent Nervous System (Campaign XVI) — human-review routing.

Slice 385.  The top of the escalation ladder (384) is a human —
but "send it to a human" without a queue, an SLA, and a timeout
policy is a ticket black hole.  :class:`HumanReviewQueue` is the
human's inbox:

- :meth:`enqueue` parks a decision with a severity and an SLA
  (seconds); the queue orders by severity then arrival;
- :meth:`decide` records approve/reject with reviewer identity —
  double decisions raise instead of silently overwriting;
- :meth:`overdue` lists items past SLA; :meth:`sweep` applies the
  timeout policy: ``"auto_deny"`` / ``"auto_approve"`` (recorded
  with reviewer ``"timeout-policy"``), ``"escalate"`` (left
  pending for the caller to escalate), or ``"raise"`` which raises
  :class:`HumanReviewTimeout` naming every overdue item;
- lifecycle events (``review.enqueued`` / ``review.decided`` /
  ``review.overdue``) go on the bus with trace continuity, so
  notification gating (382) can page the human and provenance
  (396) sees the verdict.

Severities reuse the observability ladder — a ``"critical"``
review sorts above everything, the same word the alerter uses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.bus import EventBus
from hugrgate.agents.types import AgentSignal
from hugrgate.errors import HumanReviewTimeout
from hugrgate.observability.alerts import SEVERITIES

__all__ = [
    "TIMEOUT_POLICIES",
    "HumanReviewQueue",
    "ReviewDecision",
    "ReviewItem",
]

#: Allowed timeout policies for overdue items.
TIMEOUT_POLICIES: tuple[str, ...] = (
    "escalate", "auto_deny", "auto_approve", "raise",
)

_SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}


@dataclass(frozen=True)
class ReviewItem:
    """One decision awaiting a human."""

    item_id: str
    ticket_id: str
    agent_id: str
    summary: str
    severity: str = "warning"
    sla_s: float = 3600.0
    enqueued_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id must be non-empty")
        if self.severity not in _SEVERITY_RANK:
            raise ValueError(f"unknown severity {self.severity!r}")
        if self.sla_s <= 0:
            raise ValueError("sla_s must be > 0")

    def is_overdue(self, now: float) -> bool:
        """True when ``now`` is past the item's SLA."""
        return now - self.enqueued_at > self.sla_s


@dataclass(frozen=True)
class ReviewDecision:
    """A human's (or the timeout policy's) verdict."""

    item_id: str
    approved: bool
    reviewer: str
    decided_at: float
    note: str = ""


class HumanReviewQueue:
    """The human's inbox at the top of the escalation ladder."""

    def __init__(
        self,
        bus: EventBus | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._bus = bus
        self._clock = clock or time.monotonic
        self._pending: dict[str, ReviewItem] = {}
        self._decisions: dict[str, ReviewDecision] = {}
        self._stats = {"enqueued": 0, "decided": 0, "approved": 0,
                       "rejected": 0, "overdue_sweeps": 0}

    def enqueue(self, item: ReviewItem) -> str:
        """Park ``item`` for review; returns its id."""
        if item.item_id in self._pending or item.item_id in self._decisions:
            raise ValueError(f"duplicate review item {item.item_id!r}")
        stamped = ReviewItem(
            item_id=item.item_id, ticket_id=item.ticket_id,
            agent_id=item.agent_id, summary=item.summary,
            severity=item.severity, sla_s=item.sla_s,
            enqueued_at=self._clock(), metadata=dict(item.metadata),
        )
        self._pending[stamped.item_id] = stamped
        self._stats["enqueued"] += 1
        self._emit("review.enqueued", stamped, {
            "item_id": stamped.item_id, "ticket_id": stamped.ticket_id,
            "severity": stamped.severity, "sla_s": stamped.sla_s,
        })
        return stamped.item_id

    def pending(self) -> tuple[ReviewItem, ...]:
        """Pending items: severity first, then arrival order."""
        return tuple(sorted(
            self._pending.values(),
            key=lambda i: (-_SEVERITY_RANK[i.severity], i.enqueued_at),
        ))

    def overdue(self, now: float | None = None) -> tuple[ReviewItem, ...]:
        """Pending items past their SLA, oldest-overdue first."""
        at = self._clock() if now is None else now
        return tuple(sorted(
            (i for i in self._pending.values() if i.is_overdue(at)),
            key=lambda i: i.enqueued_at,
        ))

    def decide(
        self,
        item_id: str,
        approved: bool,
        reviewer: str,
        note: str = "",
    ) -> ReviewDecision:
        """Record a verdict; raises on unknown or decided items."""
        item = self._pending.get(item_id)
        if item is None:
            if item_id in self._decisions:
                raise ValueError(
                    f"review item {item_id!r} already decided")
            raise ValueError(f"unknown review item {item_id!r}")
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer must be non-empty")
        decision = ReviewDecision(
            item_id=item_id, approved=approved, reviewer=reviewer,
            decided_at=self._clock(), note=note,
        )
        del self._pending[item_id]
        self._decisions[item_id] = decision
        self._stats["decided"] += 1
        self._stats["approved" if approved else "rejected"] += 1
        self._emit("review.decided", item, {
            "item_id": item_id, "approved": approved, "reviewer": reviewer,
        })
        return decision

    def sweep(
        self, now: float | None = None, *, on_timeout: str = "escalate"
    ) -> tuple[ReviewItem, ...]:
        """Apply the timeout policy to overdue items.

        ``"auto_deny"``/``"auto_approve"`` record verdicts as
        ``"timeout-policy"``; ``"escalate"`` leaves items pending
        (returned for the caller to escalate); ``"raise"`` raises
        :class:`HumanReviewTimeout` naming every overdue item.
        """
        if on_timeout not in TIMEOUT_POLICIES:
            raise ValueError(f"on_timeout must be one of {TIMEOUT_POLICIES}")
        at = self._clock() if now is None else now
        overdue = self.overdue(at)
        self._stats["overdue_sweeps"] += 1
        if on_timeout == "raise" and overdue:
            raise HumanReviewTimeout(
                f"{len(overdue)} review item(s) breached SLA: "
                + ", ".join(i.item_id for i in overdue),
                item_ids=[i.item_id for i in overdue],
            )
        if on_timeout in ("auto_deny", "auto_approve"):
            for item in overdue:
                self.decide(item.item_id,
                            approved=(on_timeout == "auto_approve"),
                            reviewer="timeout-policy",
                            note=f"SLA {item.sla_s}s breached")
            return ()
        for item in overdue:
            self._emit("review.overdue", item, {
                "item_id": item.item_id, "ticket_id": item.ticket_id,
                "overdue_by_s": round(at - item.enqueued_at - item.sla_s, 1),
            })
        return overdue

    def decision_for(self, item_id: str) -> ReviewDecision | None:
        """The recorded verdict for ``item_id``, if any."""
        return self._decisions.get(item_id)

    def _emit(self, topic: str, item: ReviewItem,
              payload: dict[str, Any]) -> None:
        bus = self._bus
        if bus is not None:
            bus.publish(AgentSignal(
                topic=topic, payload=payload, priority="high",
                trace_id=item.metadata.get("trace_id", ""),
                source="human-review",
            ))

    def stats(self) -> dict[str, int]:
        """Queue counters (copy)."""
        return dict(self._stats)
