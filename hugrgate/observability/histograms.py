"""Latency histograms for decision observability. Slice 336.

:class:`LatencyTracker` is the opinionated instrument for decision
latency: one histogram per backend with the campaign's standard
buckets, millisecond-facing helpers, and an SLA predicate.  It sits on
the shared :class:`MetricRegistry` so Prometheus (slice 334) and the
dashboard (slice 335) see the same numbers.

The slice's measurement artifact is produced by
``benchmarks/observability_overhead_336.py`` → 
``benchmarks/observability_overhead_336.json``: the real overhead of
the instrumented observe path, compared against the explicit baseline
(≤ 50 µs p99 per observation on the reference host).
"""

from __future__ import annotations

from typing import Any

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import (
    DEFAULT_LATENCY_BUCKETS,
    Histogram,
    MetricRegistry,
)

__all__ = [
    "LatencyTracker",
]

#: SLA percentiles reported by :meth:`LatencyTracker.summary`.
_SUMMARY_QUANTILES = (0.5, 0.9, 0.99)


class LatencyTracker:
    """Per-backend decision-latency histogram with ms-facing helpers."""

    def __init__(self, registry: MetricRegistry,
                 name: str = "hugrgate_decision_latency_seconds",
                 label_names: tuple[str, ...] = ("backend",),
                 buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS
                 ) -> None:
        self._histogram: Histogram = registry.histogram(
            name, "Decision latency in seconds", labels=label_names,
            buckets=buckets)
        self._label_names = label_names

    @property
    def histogram(self) -> Histogram:
        return self._histogram

    def _labels(self, backend: str) -> dict[str, str]:
        if "backend" not in self._label_names:
            return {}
        if not backend:
            raise MetricError("backend name must be non-empty")
        return {"backend": backend}

    def observe_ms(self, latency_ms: float, backend: str = "") -> None:
        """Record one latency observation in milliseconds."""
        if latency_ms < 0:
            raise MetricError(
                f"latency_ms must be >= 0, got {latency_ms!r}")
        self._histogram.observe(latency_ms / 1000.0,
                                self._labels(backend) or None)

    def percentile_ms(self, q: float, backend: str = "") -> float:
        """Estimated q-th percentile latency in milliseconds."""
        return self._histogram.percentile(q, self._labels(backend) or None
                                          ) * 1000.0

    def summary(self, backend: str = "") -> dict[str, Any]:
        """Count, mean, and p50/p90/p99 in milliseconds."""
        labels = self._labels(backend) or None
        count = self._histogram.count(labels)
        if count == 0:
            raise MetricError("no latency observations recorded")
        mean_ms = self._histogram.total(labels) / count * 1000.0
        out: dict[str, Any] = {"count": count, "mean_ms": mean_ms}
        for q in _SUMMARY_QUANTILES:
            out[f"p{int(q * 100)}_ms"] = self.percentile_ms(q, backend)
        return out

    def within_sla(self, budget_p99_ms: float, backend: str = "") -> bool:
        """True when the estimated p99 latency is within budget."""
        if budget_p99_ms <= 0:
            raise MetricError(
                f"budget_p99_ms must be positive, got {budget_p99_ms!r}")
        return self.percentile_ms(0.99, backend) <= budget_p99_ms
