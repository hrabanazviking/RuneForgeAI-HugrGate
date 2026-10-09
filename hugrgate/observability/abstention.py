"""Abstention metrics. Slice 338.

Abstentions are first-class observability signals: *why* the gate
refused to decide matters as much as the decisions it made.
:class:`AbstentionMetrics` counts abstentions by machine-readable
reason (the ``abstain_reason`` metadata set by
:func:`hugrgate.abstain.abstain`), reviews by policy verdict, and keeps
a bounded sliding window for recent abstention *rates*.

An abstention is never a backend failure — these counters live
alongside, not inside, the error metrics.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import Counter, MetricRegistry
from hugrgate.result import DecisionResult

__all__ = [
    "AbstentionMetrics",
]

_DEFAULT_WINDOW = 1000


class AbstentionMetrics:
    """Count abstentions by reason and reviews; sliding-window rates."""

    def __init__(self, registry: MetricRegistry | None = None,
                 window: int = _DEFAULT_WINDOW) -> None:
        if window < 1:
            raise MetricError("AbstentionMetrics window must be positive")
        self._registry = registry or MetricRegistry()
        self._window = window
        self._abstentions: Counter = self._registry.counter(
            "hugrgate_abstentions_total",
            "Abstentions by machine-readable reason",
            labels=("reason", "backend"))
        self._reviews: Counter = self._registry.counter(
            "hugrgate_reviews_total",
            "Decisions routed to human review",
            labels=("backend",))
        self._decisions = 0
        self._recent: deque[bool] = deque(maxlen=window)

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    def record(self, result: DecisionResult) -> str:
        """Record one decision result.

        Returns the recorded class: ``"abstain"``, ``"review"``, or
        ``"accept"``.
        """
        self._decisions += 1
        backend = result.backend or "unknown"
        if not result.accepted:
            reason = str(result.metadata.get("abstain_reason", "unknown"))
            self._abstentions.inc(1.0, labels={"reason": reason,
                                               "backend": backend})
            self._recent.append(True)
            return "abstain"
        self._recent.append(False)
        if str(result.metadata.get("policy_verdict", "")) == "review":
            self._reviews.inc(1.0, labels={"backend": backend})
            return "review"
        return "accept"

    def abstentions_by_reason(self, backend: str = "") -> dict[str, float]:
        """Total abstentions per reason (all backends, or one)."""
        out: dict[str, float] = {}
        # Walk the counter's series through the snapshot — the only
        # public read path (slice 326 contract).
        for series in self._registry.snapshot()["metrics"]:
            if series["name"] != "hugrgate_abstentions_total":
                continue
            for row in series["series"]:
                labels = row["labels"]
                if backend and labels.get("backend") != backend:
                    continue
                reason = labels["reason"]
                out[reason] = out.get(reason, 0.0) + row["value"]
        return out

    def summary(self) -> dict[str, Any]:
        """Totals plus sliding-window abstention rate."""
        recent = list(self._recent)
        rate = (sum(recent) / len(recent)) if recent else 0.0
        return {
            "decisions_observed": self._decisions,
            "abstention_rate_window": round(rate, 4),
            "window_size": len(recent),
            "by_reason": self.abstentions_by_reason(),
        }
