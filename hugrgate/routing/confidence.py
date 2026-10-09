"""Confidence-aware routing. Slice 055.

A rung's confidence gate is only as honest as the backend behind it: an
overconfident backend clears gates it has not earned. This module makes
routing *confidence-aware* in two ways:

1. **Plan-time gate adjustment** — :class:`ConfidenceAwarePlanner` wraps
   any planner and widens each rung's ``min_confidence`` by the backend's
   expected calibration error (from ``calibration_info()["ece"]`` or a
   :class:`CalibrationTracker`). An overconfident backend must clear a
   higher bar; a well-calibrated one keeps its gate.
2. **Runtime calibration tracking** — :class:`CalibrationTracker`
   records ``(reported probability, actual correctness)`` pairs per
   backend and computes the expected calibration error (ECE) over
   probability bins, the standard statistical measure of miscalibration.

Metric/coverage assumptions (validated statistically in the tests):
ECE is computed over 10 equal-width bins as Σ |acc − conf| · n/N.
A perfectly calibrated backend has ECE ≈ 0; a backend reporting 0.9
while correct 70% of the time has ECE ≈ 0.2. Gates are widened
additively and clamped to [0,1]; widening never *lowers* a gate.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hugrgate.backend import Backend
from hugrgate.routing.architecture import (RouterContext, RungNode,
                                            RungPlanner, RoutingPlan)

__all__ = [
    "CalibrationTracker",
    "ConfidenceAwarePlanner",
    "adjusted_gate",
]


def adjusted_gate(base_gate: float, ece: float) -> float:
    """Widen a confidence gate by the expected calibration error."""
    if not 0.0 <= base_gate <= 1.0:
        raise ValueError(f"base_gate out of [0,1]: {base_gate}")
    if ece < 0:
        raise ValueError(f"ece must be non-negative, got {ece}")
    return min(1.0, base_gate + ece)


class CalibrationTracker:
    """Per-backend (probability, correctness) ledger with ECE computation."""

    def __init__(self, n_bins: int = 10):
        if n_bins < 1:
            raise ValueError("n_bins must be >= 1")
        self.n_bins = n_bins
        self._samples: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)

    def record(self, backend_name: str, probability: float,
               correct: bool) -> None:
        """Record one judged outcome. Correctness comes from graded
        outcomes (evals, human review, downstream verification) — never
        guessed."""
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"probability out of [0,1]: {probability}")
        self._samples[backend_name].append((probability, bool(correct)))

    def samples(self, backend_name: str) -> int:
        return len(self._samples[backend_name])

    def ece(self, backend_name: str) -> float:
        """Expected calibration error over equal-width probability bins."""
        samples = self._samples[backend_name]
        if not samples:
            return 0.0
        n = len(samples)
        total = 0.0
        for b in range(self.n_bins):
            lo, hi = b / self.n_bins, (b + 1) / self.n_bins
            in_bin = [s for s in samples
                      if (lo <= s[0] < hi) or (b == self.n_bins - 1
                                              and s[0] == hi)]
            if not in_bin:
                continue
            acc = sum(1 for _, c in in_bin if c) / len(in_bin)
            conf = sum(p for p, _ in in_bin) / len(in_bin)
            total += abs(acc - conf) * (len(in_bin) / n)
        return round(total, 4)

    def gate_for(self, backend_name: str, base_gate: float) -> float:
        """Base gate widened by this backend's measured ECE."""
        return adjusted_gate(base_gate, self.ece(backend_name))


class ConfidenceAwarePlanner(RungPlanner):
    """Wrap a planner; widen each rung's gate by the backend's ECE.

    ECE source precedence: the tracker's measured ECE (when it holds at
    least ``min_samples``), else the backend's declared
    ``calibration_info()["ece"]``, else 0.
    """

    def __init__(self, inner: RungPlanner, registry,
                 tracker: Optional[CalibrationTracker] = None,
                 min_samples: int = 50):
        self.inner = inner
        self.registry = registry
        self.tracker = tracker or CalibrationTracker()
        self.min_samples = min_samples

    def _ece_for(self, backend: Backend) -> float:
        if self.tracker.samples(backend.name) >= self.min_samples:
            return self.tracker.ece(backend.name)
        ece = (backend.calibration_info() or {}).get("ece", 0.0)
        return float(ece) if isinstance(ece, (int, float)) and ece >= 0 else 0.0

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        nodes: List[RungNode] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            if backend is None:
                nodes.append(node)
                continue
            ece = self._ece_for(backend)
            widened = adjusted_gate(node.min_confidence, ece)
            nodes.append(RungNode(
                node.backend_name, widened, node.latency_budget_ms,
                node.mode,
                why=(node.why + f"; confidence-aware gate "
                     f"{node.min_confidence:.2f}→{widened:.2f} (ece={ece:.3f})"
                     if ece > 0 else node.why),
                params={**node.params, "ece": ece,
                        "base_gate": node.min_confidence}))
        plan.nodes = nodes
        plan.created_by = f"{plan.created_by}+confidence"
        plan.rationale.append(
            "gates widened by per-backend expected calibration error")
        return plan
