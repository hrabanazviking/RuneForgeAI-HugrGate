"""Health dashboard data. Slice 335.

The dashboard is the *aggregation* layer: it funnels one
:func:`observe` call per decision into the :class:`HealthMonitor`
(per-backend health, quarantine) and the :class:`MetricRegistry`
(counters, latency histograms), and :meth:`snapshot` rolls those up —
plus firing alerts (slice 343) and SLO statuses (slice 345), passed in
at snapshot time so this module never depends on the alert/SLO
modules — into one JSON-serializable document:

``status`` is ``"healthy"`` / ``"degraded"`` / ``"critical"``:

- ``critical`` — any backend quarantined, or any firing alert with
  severity ``"critical"``;
- ``degraded`` — any firing ``"warning"`` alert, or any backend score
  below 0.5;
- ``healthy`` — otherwise.

The dashboard never invents numbers: every field derives from recorded
observations.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from hugrgate.errors import MetricError
from hugrgate.health import HealthMonitor
from hugrgate.observability.metrics import (
    DEFAULT_LATENCY_BUCKETS,
    Counter,
    Histogram,
    MetricRegistry,
)

__all__ = [
    "VERDICTS",
    "HealthDashboard",
]

#: The only verdict label values the dashboard accepts.
VERDICTS = ("accept", "review", "abstain")

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


class HealthDashboard:
    """Aggregate decisions into health scores, metrics, and a snapshot."""

    def __init__(self, registry: MetricRegistry | None = None,
                 health: HealthMonitor | None = None) -> None:
        self._registry = registry or MetricRegistry()
        self._health = health or HealthMonitor()
        self._lock = threading.Lock()
        self._backends: dict[str, None] = {}
        self._decisions: Counter = self._registry.counter(
            "hugrgate_decisions_total",
            "Decisions observed by the health dashboard",
            labels=("backend", "verdict"))
        self._latency: Histogram = self._registry.histogram(
            "hugrgate_decision_latency_seconds",
            "Decision latency observed by the health dashboard",
            labels=("backend",),
            buckets=DEFAULT_LATENCY_BUCKETS)

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    @property
    def health(self) -> HealthMonitor:
        return self._health

    def observe(self, backend: str, latency_ms: float,
                ok: bool = True, verdict: str = "accept") -> None:
        """Record one decision outcome.

        *verdict* must be one of ``accept`` / ``review`` / ``abstain``;
        *ok* marks backend success for health scoring (an abstention is
        not a backend failure — pass ``ok=True`` with
        ``verdict="abstain"``).
        """
        if verdict not in VERDICTS:
            raise MetricError(
                f"unknown verdict {verdict!r}: expected one of "
                f"{list(VERDICTS)}")
        if not backend:
            raise MetricError("backend name must be non-empty")
        if latency_ms < 0:
            raise MetricError(f"latency_ms must be >= 0, got {latency_ms!r}")
        self._health.record(backend, latency_ms, ok=ok)
        self._decisions.inc(1.0, labels={"backend": backend,
                                         "verdict": verdict})
        self._latency.observe(latency_ms / 1000.0,
                              labels={"backend": backend})
        with self._lock:
            self._backends.setdefault(backend, None)

    def _status(self, quarantined: list[str],
                alerts: list[dict[str, Any]]) -> str:
        worst = 0
        for alert in alerts:
            worst = max(worst,
                        _SEVERITY_RANK.get(str(alert.get("severity",
                                                         "info")), 0))
        if quarantined or worst >= 2:
            return "critical"
        if worst >= 1:
            return "degraded"
        with self._lock:
            names = list(self._backends)
        for name in names:
            if self._health.score(name) < 0.5:
                return "degraded"
        return "healthy"

    def snapshot(self, alerts: list[dict[str, Any]] | None = None,
                 slo_statuses: list[dict[str, Any]] | None = None
                 ) -> dict[str, Any]:
        """Build the dashboard document (JSON-serializable)."""
        alerts = list(alerts or [])
        slo_statuses = list(slo_statuses or [])
        with self._lock:
            names = list(self._backends)
        quarantined = self._health.quarantined()
        backends: dict[str, Any] = {}
        totals = {"decisions": 0, "quarantined_backends": len(quarantined)}
        for name in names:
            stats = self._health.stats(name)
            score = self._health.score(name)
            decisions = int(sum(
                self._decisions.value(labels={"backend": name, "verdict": v})
                for v in VERDICTS))
            totals["decisions"] += decisions
            backends[name] = {
                "score": round(score, 4),
                "quarantined": name in quarantined,
                "p50_ms": round(stats["p50_ms"], 3),
                "p99_ms": round(stats["p99_ms"], 3),
                "error_rate": round(stats["error_rate"], 4),
                "consecutive_failures": stats["consecutive_failures"],
                "samples": stats["samples"],
                "decisions_total": decisions,
                "latency_p50_s": round(
                    self._latency.percentile(0.5,
                                             labels={"backend": name}), 6)
                if self._latency.count(labels={"backend": name}) else 0.0,
            }
        return {
            "generated_at": time.time(),
            "status": self._status(quarantined, alerts),
            "backends": backends,
            "totals": totals,
            "firing_alerts": alerts,
            "slos": slo_statuses,
        }
