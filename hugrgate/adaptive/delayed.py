"""Delayed-label ingestion. Slice 128.

Outcomes rarely arrive with the decision. Human grades, downstream
success signals, and batch evaluations land seconds, minutes, or hours
later — and occasionally *before* the telemetry line that describes the
decision (out-of-order streams). :class:`DelayedLabelIngestion` is the
patient join:

- :meth:`ingest` applies a label immediately when its telemetry is
  present; otherwise the label waits in a bounded pending queue.
- :meth:`drain` retries pending labels whose telemetry has since
  arrived (called automatically on every ingest).
- :meth:`sweep` expires pending labels older than ``ttl_s`` and reports
  how many were dropped — silent loss is a data-quality bug, so drops
  are counted, never swallowed.
- Labels for decisions that will never be logged are rejected with
  ``KeyError`` from the feedback API; here they wait, because in a
  streaming world "not yet" and "never" look identical until the TTL
  expires.

Stale labels are also guarded: a label carrying a ``received_at`` older
than ``ttl_s`` relative to *now* is expired on arrival rather than
applied to a decision it can no longer fairly describe.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hugrgate.errors import SpecError

from hugrgate.adaptive.feedback import OutcomeFeedbackAPI, OutcomeRecord

__all__ = [
    "DelayedLabel",
    "DelayedLabelIngestion",
    "SweepReport",
]


@dataclass(frozen=True)
class DelayedLabel:
    """An outcome label in flight toward its telemetry event."""

    request_id: str
    quality: float
    label: Optional[str] = None
    source: str = "human"
    received_at: float = field(default_factory=time.time)

    def age(self, now: Optional[float] = None) -> float:
        return (time.time() if now is None else now) - self.received_at


@dataclass
class SweepReport:
    """What :meth:`DelayedLabelIngestion.sweep` did."""

    applied: int = 0
    expired: int = 0
    still_pending: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "expired": self.expired,
            "still_pending": self.still_pending,
        }


class DelayedLabelIngestion:
    """Joins late (or early) outcome labels with routing telemetry."""

    def __init__(self, feedback: OutcomeFeedbackAPI, *,
                 ttl_s: float = 3600.0,
                 max_pending: int = 10_000) -> None:
        if ttl_s <= 0:
            raise SpecError(f"ttl_s must be positive, got {ttl_s}")
        if max_pending <= 0:
            raise SpecError(f"max_pending must be positive, got {max_pending}")
        self.feedback = feedback
        self.ttl_s = ttl_s
        self.max_pending = max_pending
        self._pending: "OrderedDict[str, DelayedLabel]" = OrderedDict()
        self.dropped_expired = 0

    def __len__(self) -> int:
        return len(self._pending)

    def ingest(self, label: DelayedLabel,
               now: Optional[float] = None) -> str:
        """Accept a label; returns ``"applied"``, ``"pending"`` or
        ``"expired"``."""
        now = time.time() if now is None else now
        # Validate the label shape up front — a malformed label must
        # never sit in the queue.
        OutcomeRecord(request_id=label.request_id, quality=label.quality,
                      label=label.label, source=label.source,
                      received_at=label.received_at)
        if label.age(now) > self.ttl_s:
            self.dropped_expired += 1
            return "expired"
        if label.request_id in self.feedback.store:
            event = self.feedback.store.get(label.request_id)
            assert event is not None
            if event.labeled:
                # Already has an outcome: the late duplicate is stale.
                self.dropped_expired += 1
                return "expired"
            self.feedback.record_outcome(
                label.request_id, quality=label.quality, label=label.label,
                source=label.source, received_at=label.received_at)
            self._pending.pop(label.request_id, None)
            return "applied"
        if label.request_id in self._pending:
            # Keep the earliest arrival; duplicates don't extend the TTL.
            return "pending"
        if len(self._pending) >= self.max_pending:
            raise SpecError(
                f"pending queue full ({self.max_pending}); sweep or drain "
                f"before ingesting more labels")
        self._pending[label.request_id] = label
        return "pending"

    def drain(self, now: Optional[float] = None) -> int:
        """Apply every pending label whose telemetry has arrived."""
        now = time.time() if now is None else now
        applied = 0
        for request_id in list(self._pending):
            label = self._pending[request_id]
            if label.age(now) > self.ttl_s:
                continue  # sweep() owns expiry accounting
            if request_id in self.feedback.store:
                event = self.feedback.store.get(request_id)
                if event is not None and not event.labeled:
                    self.feedback.record_outcome(
                        request_id, quality=label.quality, label=label.label,
                        source=label.source, received_at=label.received_at)
                    applied += 1
                if event is not None and event.labeled:
                    # Telemetry arrived already labeled (e.g. via the
                    # immediate path): the pending duplicate is stale.
                    self.dropped_expired += 1
                del self._pending[request_id]
        return applied

    def sweep(self, now: Optional[float] = None) -> SweepReport:
        """Expire stale pending labels; apply the rest that now match."""
        now = time.time() if now is None else now
        report = SweepReport()
        for request_id in list(self._pending):
            label = self._pending[request_id]
            if label.age(now) > self.ttl_s:
                del self._pending[request_id]
                report.expired += 1
                self.dropped_expired += 1
            elif request_id in self.feedback.store:
                event = self.feedback.store.get(request_id)
                if event is not None and not event.labeled:
                    self.feedback.record_outcome(
                        request_id, quality=label.quality, label=label.label,
                        source=label.source, received_at=label.received_at)
                    report.applied += 1
                del self._pending[request_id]
        report.still_pending = len(self._pending)
        return report

    def pending_ids(self) -> List[str]:
        return list(self._pending)
