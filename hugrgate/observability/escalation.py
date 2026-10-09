"""Escalation metrics. Slice 339.

Worker supervision (:mod:`hugrgate.supervision`) restarts dead workers
and *escalates* when a restart budget is exhausted.  This module makes
both visible: restarts by worker, escalations by worker and reason,
and a bounded history of escalation events for the dashboard and the
explanation report.

Wire-up is a one-liner — the metrics object *is* the callback::

    metrics = EscalationMetrics()
    supervisor = Supervisor(on_escalation=metrics.as_callback(), ...)
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import Counter, MetricRegistry

__all__ = [
    "MAX_HISTORY",
    "EscalationMetrics",
]

#: Bound on the retained escalation-event history.
MAX_HISTORY = 500


class EscalationMetrics:
    """Count worker restarts and escalations; retain recent events."""

    def __init__(self, registry: MetricRegistry | None = None) -> None:
        self._registry = registry or MetricRegistry()
        self._restarts: Counter = self._registry.counter(
            "hugrgate_worker_restarts_total",
            "Worker restarts by worker name",
            labels=("worker",))
        self._escalations: Counter = self._registry.counter(
            "hugrgate_worker_escalations_total",
            "Worker escalations by worker and reason",
            labels=("worker", "reason"))
        self._lock = threading.Lock()
        self._history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    def _check_worker(self, worker: str) -> str:
        if not worker:
            raise MetricError("worker name must be non-empty")
        return worker

    def record_restart(self, worker: str) -> None:
        """Record one worker restart."""
        self._restarts.inc(1.0,
                           labels={"worker": self._check_worker(worker)})

    def record_escalation(self, worker: str, reason: str) -> None:
        """Record one escalation (restart budget exhausted)."""
        worker = self._check_worker(worker)
        if not reason:
            raise MetricError("escalation reason must be non-empty")
        self._escalations.inc(1.0, labels={"worker": worker,
                                           "reason": reason})
        with self._lock:
            self._history.append({
                "timestamp": time.time(),
                "worker": worker,
                "reason": reason,
            })

    def as_callback(self) -> Any:
        """Return an ``on_escalation`` callback for :class:`Supervisor`."""

        def _on_escalation(name: str, reason: str,
                           record: Any) -> None:
            self.record_escalation(name, reason)

        return _on_escalation

    def restarts(self, worker: str) -> float:
        return self._restarts.value(labels={"worker": worker})

    def recent_escalations(self, limit: int = 50) -> list[dict[str, Any]]:
        """Newest-first escalation events (bounded history)."""
        if limit < 1:
            raise MetricError("limit must be positive")
        with self._lock:
            events = list(self._history)
        return events[-limit:][::-1]

    def summary(self) -> dict[str, Any]:
        total_restarts = 0.0
        total_escalations = 0.0
        for metric in self._registry.snapshot()["metrics"]:
            for row in metric["series"]:
                if metric["name"] == "hugrgate_worker_restarts_total":
                    total_restarts += row["value"]
                elif metric["name"] == "hugrgate_worker_escalations_total":
                    total_escalations += row["value"]
        with self._lock:
            history_len = len(self._history)
        return {
            "total_restarts": total_restarts,
            "total_escalations": total_escalations,
            "escalation_history_retained": history_len,
        }
