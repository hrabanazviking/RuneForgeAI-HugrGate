"""Cost metrics. Slice 340.

Every routed decision can carry a cost (see
:attr:`RouteEvent.cost <hugrgate.adaptive.telemetry.RouteEvent>`).
:class:`CostMetrics` aggregates spend: totals, per-backend, per-route
totals, and a bounded ledger of recent charges for audit.

Costs are non-negative floats in a single configured currency unit
(``currency`` is a label, not a converter — HugrGate never invents FX
rates).  Negative costs raise :class:`~hugrgate.errors.MetricError`.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import Counter, MetricRegistry

__all__ = [
    "MAX_LEDGER",
    "CostMetrics",
]

#: Bound on the retained charge ledger.
MAX_LEDGER = 1000


class CostMetrics:
    """Aggregate decision costs by backend and route."""

    def __init__(self, registry: MetricRegistry | None = None,
                 currency: str = "USD") -> None:
        if not currency:
            raise MetricError("currency must be non-empty")
        self._currency = currency
        self._registry = registry or MetricRegistry()
        self._spend: Counter = self._registry.counter(
            "hugrgate_cost_total",
            "Decision cost by backend and route",
            labels=("backend", "route", "currency"))
        self._lock = threading.Lock()
        self._ledger: deque[dict[str, Any]] = deque(maxlen=MAX_LEDGER)

    @property
    def currency(self) -> str:
        return self._currency

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    def record(self, cost: float, backend: str,
               route: str = "direct") -> None:
        """Record one charge.  *cost* must be finite and non-negative."""
        if not isinstance(cost, (int, float)) or cost != cost:
            raise MetricError(f"cost must be a finite number, got {cost!r}")
        if cost < 0:
            raise MetricError(f"cost must be non-negative, got {cost!r}")
        if not backend:
            raise MetricError("backend name must be non-empty")
        if not route:
            raise MetricError("route must be non-empty")
        self._spend.inc(float(cost), labels={
            "backend": backend, "route": route, "currency": self._currency})
        with self._lock:
            self._ledger.append({
                "timestamp": time.time(),
                "backend": backend,
                "route": route,
                "cost": float(cost),
                "currency": self._currency,
            })

    def total(self, backend: str = "", route: str = "") -> float:
        """Total spend, optionally filtered by backend and/or route."""
        total = 0.0
        for metric in self._registry.snapshot()["metrics"]:
            if metric["name"] != "hugrgate_cost_total":
                continue
            for row in metric["series"]:
                labels = row["labels"]
                if backend and labels.get("backend") != backend:
                    continue
                if route and labels.get("route") != route:
                    continue
                total += row["value"]
        return total

    def recent_charges(self, limit: int = 50) -> list[dict[str, Any]]:
        """Newest-first charge ledger (bounded)."""
        if limit < 1:
            raise MetricError("limit must be positive")
        with self._lock:
            charges = list(self._ledger)
        return charges[-limit:][::-1]

    def summary(self) -> dict[str, Any]:
        by_backend: dict[str, float] = {}
        for metric in self._registry.snapshot()["metrics"]:
            if metric["name"] != "hugrgate_cost_total":
                continue
            for row in metric["series"]:
                name = row["labels"]["backend"]
                by_backend[name] = by_backend.get(name, 0.0) + row["value"]
        with self._lock:
            ledger_len = len(self._ledger)
        return {
            "currency": self._currency,
            "total": round(self.total(), 6),
            "by_backend": {k: round(v, 6)
                           for k, v in sorted(by_backend.items())},
            "charges_retained": ledger_len,
        }
