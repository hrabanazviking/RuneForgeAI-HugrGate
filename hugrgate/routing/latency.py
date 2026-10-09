"""Latency-aware routing. Slice 056.

Declared ``backend.estimated_latency()`` values are guesses — often the
100ms conservative default. This module learns the truth: a
:class:`LatencyTracker` keeps an exponential moving average of *measured*
rung latencies per backend, and routing uses the measured EMA once enough
samples exist, falling back to the declared estimate before that.

- :class:`LatencyTracker.record` / :meth:`estimate` — EMA (α=0.3) with a
  minimum-sample gate.
- :class:`LatencyAwarePlanner` — wraps any planner; at plan time it
  prunes rungs whose *measured* estimate already exceeds the policy's
  latency budget, and stamps each surviving node with the estimate it
  used (``params["latency_estimate_ms"]``), so the plan shows its work.
- :meth:`LadderRouterV2.note_latencies` — called by executors after each
  climb to feed measured rung latencies back into the tracker.

The reproducible measurement artifact lives in
``benchmarks/routing_latency_056.py`` → ``benchmarks/routing_latency_056.json``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungNode,
                                            RungPlanner, RoutingPlan)

__all__ = [
    "LatencyTracker",
    "LatencyAwarePlanner",
]


class LatencyTracker:
    """Per-backend EMA of measured rung latencies (milliseconds)."""

    def __init__(self, alpha: float = 0.3, min_samples: int = 3):
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0,1], got {alpha}")
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        self.alpha = alpha
        self.min_samples = min_samples
        self._ema: Dict[str, float] = {}
        self._n: Dict[str, int] = {}

    def record(self, backend_name: str, latency_ms: float) -> None:
        if latency_ms < 0:
            raise ValueError(f"latency_ms must be non-negative, "
                             f"got {latency_ms}")
        n = self._n.get(backend_name, 0) + 1
        self._n[backend_name] = n
        if backend_name in self._ema:
            self._ema[backend_name] = (self.alpha * latency_ms
                                       + (1 - self.alpha)
                                       * self._ema[backend_name])
        else:
            self._ema[backend_name] = latency_ms

    def samples(self, backend_name: str) -> int:
        return self._n.get(backend_name, 0)

    def measured(self, backend_name: str) -> Optional[float]:
        """EMA once enough samples exist, else None."""
        if self._n.get(backend_name, 0) >= self.min_samples:
            return round(self._ema[backend_name], 3)
        return None

    def estimate(self, backend: Backend) -> float:
        """Measured EMA when available; declared estimate otherwise."""
        measured = self.measured(backend.name)
        if measured is not None:
            return measured
        return float(backend.estimated_latency())


class LatencyAwarePlanner(RungPlanner):
    """Wrap a planner; prune rungs the *measured* latency already rules out.

    A rung is pruned at plan time when the policy sets
    ``maximum_latency_ms`` and the tracker's estimate for that backend
    exceeds it. Surviving nodes carry ``params["latency_estimate_ms"]``.
    The executor's :meth:`skip_reason` still re-checks at run time.
    """

    def __init__(self, inner: RungPlanner, registry,
                 tracker: Optional[LatencyTracker] = None):
        self.inner = inner
        self.registry = registry
        self.tracker = tracker or LatencyTracker()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        budget = ctx.policy.maximum_latency_ms
        kept: List[RungNode] = []
        pruned: List[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            estimate = (self.tracker.estimate(backend)
                        if backend is not None else None)
            node.params["latency_estimate_ms"] = estimate
            if (budget is not None and estimate is not None
                    and estimate > budget):
                pruned.append(
                    f"{node.backend_name}: measured ~{estimate:.1f}ms "
                    f"> budget {budget:.1f}ms")
                continue
            kept.append(node)
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+latency"
        if pruned:
            plan.rationale.append(
                f"latency-pruned {len(pruned)} rung(s): "
                + "; ".join(pruned))
        else:
            plan.rationale.append("no rungs latency-pruned")
        return plan
