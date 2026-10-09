"""Latency-budget tuner. Slice 456.

A decision pipeline has per-stage latency budgets (routing, backend,
calibration, ...) that must sum to a total budget. The naive baseline
is an *equal split*; this tuner does better by measuring.

Given measured per-stage latency samples, the tuner:

1. estimates each stage's empirical tail P(X > b) from the samples;
2. seeds the allocation proportional to each stage's p99 (slow stages
   get more budget);
3. refines with coordinate descent on the simplex, minimizing the
   joint overflow probability ``1 - prod(1 - p_i)``;
4. compares against the explicit **equal-split baseline measured on
   the same samples** and proposes only on a real win.

The comparison is the reproducible measurement artifact: baseline and
tuned overflow are both computed from the recorded samples, stored in
the proposal evidence, and re-derivable by re-running the tuner with
the same seed. No numbers are invented — every figure traces to the
input samples.

Assumptions (recorded in evidence): stage latencies are treated as
independent for the joint-overflow estimate; samples are i.i.d. with
deployment traffic; budgets are in milliseconds.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.errors import TunerError

__all__ = ["LatencyBudgetTuner", "empirical_tail", "quantile"]


def quantile(samples: Sequence[float], q: float) -> float:
    """Empirical quantile (linear interpolation)."""
    if not samples:
        raise TunerError("quantile of empty samples")
    if not 0.0 <= q <= 1.0:
        raise TunerError("q must be in [0, 1]", q=q)
    xs = sorted(samples)
    pos = q * (len(xs) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def empirical_tail(samples: Sequence[float], budget: float) -> float:
    """Fraction of samples exceeding the budget."""
    if not samples:
        raise TunerError("tail of empty samples")
    return sum(1 for x in samples if x > budget) / len(samples)


@dataclass
class LatencyBudgetTuner(BaseTuner):
    """Split a total latency budget across pipeline stages."""

    name: str = "latency_budget_tuner"
    stages: Sequence[str] = field(default_factory=list)
    samples: Mapping[str, Sequence[float]] = field(default_factory=dict)
    total_budget_ms: float = 1000.0
    seed_quantile: float = 0.99
    refine_steps: int = 200
    step_ms: float = 1.0
    min_stage_ms: float = 1.0

    def __post_init__(self) -> None:
        if not self.param:
            # param is unused: this tuner writes one param per stage.
            self.param = ",".join(self.stages)
        if not self.objective_id:
            raise TunerError("latency tuner needs an objective_id")
        if len(self.stages) < 2:
            raise TunerError("need at least 2 stages", stages=self.stages)
        if len(set(self.stages)) != len(self.stages):
            raise TunerError("duplicate stage names")
        for st in self.stages:
            xs = self.samples.get(st)
            if not xs or len(xs) < 20:
                raise TunerError("each stage needs >= 20 samples", stage=st)
            if any((not isinstance(x, (int, float)) or x < 0
                    or not math.isfinite(x)) for x in xs):
                raise TunerError("samples must be finite non-negative",
                                 stage=st)
        if self.total_budget_ms <= 0:
            raise TunerError("total budget must be positive")
        if self.min_stage_ms * len(self.stages) > self.total_budget_ms:
            raise TunerError("total budget below minimum stage allocation")

    def _overflow(self, budgets: Mapping[str, float]) -> float:
        joint_ok = 1.0
        for st in self.stages:
            joint_ok *= 1.0 - empirical_tail(self.samples[st],
                                             budgets[st])
        return 1.0 - joint_ok

    def tune(self, ctx: TuningContext) -> Proposal | None:
        for st in self.stages:
            param = ctx.store.describe(st)
            if param.dtype != "float":
                raise TunerError("latency tuner needs float stage params",
                                 stage=st)
        # Seed: proportional to each stage's p99.
        q99 = {st: quantile(self.samples[st], self.seed_quantile)
               for st in self.stages}
        total_q = sum(q99.values())
        budgets = {st: max(self.min_stage_ms,
                           self.total_budget_ms * q / total_q)
                   for st, q in q99.items()}
        # Renormalize to the exact total.
        scale = self.total_budget_ms / sum(budgets.values())
        budgets = {st: b * scale for st, b in budgets.items()}
        # Coordinate descent on the simplex.
        rng = self._rng(ctx)
        order = list(self.stages)
        best = self._overflow(budgets)
        for _ in range(self.refine_steps):
            rng.shuffle(order)
            improved = False
            for i, a in enumerate(order):
                b = order[(i + 1) % len(order)]
                if budgets[a] - self.step_ms < self.min_stage_ms:
                    continue
                cand = dict(budgets)
                cand[a] -= self.step_ms
                cand[b] += self.step_ms
                val = self._overflow(cand)
                if val < best - 1e-12:
                    budgets, best = cand, val
                    improved = True
            if not improved:
                break
        # Explicit baseline: equal split, measured on the same samples.
        equal = {st: self.total_budget_ms / len(self.stages)
                 for st in self.stages}
        base_overflow = self._overflow(equal)
        evidence: dict[str, Any] = {
            "stages": list(self.stages),
            "total_budget_ms": self.total_budget_ms,
            "baseline": {"allocation": equal,
                         "joint_overflow": base_overflow},
            "tuned": {"allocation": dict(budgets),
                      "joint_overflow": best},
            "n_samples": {st: len(self.samples[st])
                          for st in self.stages},
            "assumptions": (
                "stage latencies treated as independent for the joint "
                "overflow estimate; samples i.i.d. with deployment "
                "traffic; budgets in milliseconds"),
        }
        # Negated overflow so "higher is better" like every objective.
        return self._propose(ctx, dict(budgets), -base_overflow, -best,
                             evidence)
