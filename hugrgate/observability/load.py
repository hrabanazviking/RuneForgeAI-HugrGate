"""Observability load tests. Slice 348.

Answers the only load question that matters for an observability
layer: *how much does watching cost?*  :class:`ObservabilityLoadHarness`
runs N iterations of the fully instrumented decision path (tracer +
decision/backend spans + dashboard observation + metric recording)
against a bare baseline, and reports per-iteration overhead with p50 /
p99 / max.

The harness is honest about what it measures: CPython wall-clock on
one host, not production tail latency.  :meth:`assert_within_budget`
turns the measurement into a gate — the suite (and CI) fails loudly if
instrumentation ever costs more than the declared budget.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import MetricError, ObservabilityError
from hugrgate.observability.dashboard import HealthDashboard
from hugrgate.observability.metrics import MetricRegistry
from hugrgate.observability.spans_backend import backend_span
from hugrgate.observability.spans_decision import (
    annotate_decision,
    decision_span,
)
from hugrgate.observability.trace import Tracer
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DEFAULT_BUDGET_P99_US",
    "LoadResult",
    "ObservabilityLoadHarness",
]

#: Default gate: instrumented path p99 overhead per decision.
DEFAULT_BUDGET_P99_US = 500.0


@dataclass(frozen=True)
class LoadResult:
    """Outcome of one load run."""

    n: int
    instrumented_p50_us: float
    instrumented_p99_us: float
    instrumented_max_us: float
    baseline_p50_us: float
    baseline_p99_us: float
    overhead_p99_us: float
    budget_p99_us: float
    within_budget: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "instrumented_p50_us": round(self.instrumented_p50_us, 3),
            "instrumented_p99_us": round(self.instrumented_p99_us, 3),
            "instrumented_max_us": round(self.instrumented_max_us, 3),
            "baseline_p50_us": round(self.baseline_p50_us, 3),
            "baseline_p99_us": round(self.baseline_p99_us, 3),
            "overhead_p99_us": round(self.overhead_p99_us, 3),
            "budget_p99_us": self.budget_p99_us,
            "within_budget": self.within_budget,
        }


class ObservabilityLoadHarness:
    """Measure the cost of the instrumented decision path."""

    def __init__(self, budget_p99_us: float = DEFAULT_BUDGET_P99_US,
                 warmup: int = 200) -> None:
        if budget_p99_us <= 0:
            raise MetricError("budget_p99_us must be positive")
        if warmup < 0:
            raise MetricError("warmup must be non-negative")
        self._budget_p99_us = budget_p99_us
        self._warmup = warmup

    @staticmethod
    def _percentile(sorted_values: list[float], pct: float) -> float:
        if not sorted_values:
            return 0.0
        rank = max(1, int(-(-pct * len(sorted_values) // 1)))
        return sorted_values[min(rank, len(sorted_values)) - 1]

    def _instrumented_once(self, tracer: Tracer, dashboard: HealthDashboard,
                           spec: DecisionSpec, policy: DecisionPolicy,
                           result: DecisionResult) -> None:
        with tracer.trace("load.decision"):
            with decision_span(tracer, spec, policy) as dspan:
                annotate_decision(dspan, spec, result, policy)
                with backend_span(tracer, "stub", attempt=1,
                                  parent=dspan):
                    pass
            dashboard.observe("stub", result.latency_ms, ok=True,
                              verdict="accept")

    def run(self, n: int = 1000) -> LoadResult:
        """Run *n* instrumented iterations vs a bare baseline."""
        if n < 1:
            raise MetricError("n must be positive")
        tracer = Tracer()
        dashboard = HealthDashboard(registry=MetricRegistry(max_series=100000))
        spec = DecisionSpec(type="categorical", options=["a", "b"])
        policy = DecisionPolicy(minimum_probability=0.5)
        result = DecisionResult(
            value="a", probability=0.9,
            distribution={"a": 0.9, "b": 0.1}, backend="stub",
            latency_ms=5.0)

        def instrumented() -> None:
            self._instrumented_once(tracer, dashboard, spec, policy,
                                    result)

        def baseline() -> None:
            pass

        for _ in range(self._warmup):
            instrumented()
        instrumented_samples = []
        for _ in range(n):
            start = time.perf_counter()
            instrumented()
            instrumented_samples.append(
                (time.perf_counter() - start) * 1e6)
        baseline_samples = []
        for _ in range(n):
            start = time.perf_counter()
            baseline()
            baseline_samples.append((time.perf_counter() - start) * 1e6)

        ordered = sorted(instrumented_samples)
        base_ordered = sorted(baseline_samples)
        p99 = self._percentile(ordered, 0.99)
        base_p99 = self._percentile(base_ordered, 0.99)
        overhead = max(0.0, p99 - base_p99)
        load_result = LoadResult(
            n=n,
            instrumented_p50_us=statistics.median(instrumented_samples),
            instrumented_p99_us=p99,
            instrumented_max_us=max(instrumented_samples),
            baseline_p50_us=statistics.median(baseline_samples),
            baseline_p99_us=base_p99,
            overhead_p99_us=overhead,
            budget_p99_us=self._budget_p99_us,
            within_budget=overhead <= self._budget_p99_us,
        )
        # Prove the harness really instrumented: the dashboard must
        # have seen every iteration (warmup + measured).
        total = dashboard.snapshot()["totals"]["decisions"]
        if total != n + self._warmup:
            raise ObservabilityError(
                f"load harness recorded {total} decisions, expected "
                f"{n + self._warmup}")
        return load_result

    def assert_within_budget(self, result: LoadResult) -> LoadResult:
        """Raise unless the load result is within budget (the gate)."""
        if not result.within_budget:
            raise ObservabilityError(
                f"observability overhead {result.overhead_p99_us:.1f}us "
                f"p99 exceeds budget {result.budget_p99_us:.1f}us "
                f"(n={result.n})")
        return result
