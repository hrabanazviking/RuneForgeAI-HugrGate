"""Batch-size tuner. Slice 458.

Throughput as a function of batch size saturates: each batch pays a
fixed cost plus a per-item cost. This tuner *fits* that curve from
measured (batch_size, latency, memory) samples instead of assuming
it, then picks the batch size maximizing modeled throughput subject
to latency and memory caps.

Model (least squares on the samples):

- ``latency(b) = a + c * b`` (fixed + per-item cost),
- ``memory(b) = m0 + m1 * b``,
- ``throughput(b) = b / latency(b)``.

Feasible candidates are powers of two inside the parameter bounds
(plus the bound endpoints), filtered by
``latency_hat(b) <= latency_cap`` and ``memory_hat(b) <= memory_cap``.
A proposal requires the modeled win over the current batch size to
clear ``min_delta`` *and* the latency fit to explain the data
(R² >= 0.5) — a tuner that cannot trust its model stays silent.

Evidence carries the fitted coefficients, R² values, and the
baseline-vs-tuned comparison, so the numbers are re-derivable from
the input samples.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.errors import TunerError

__all__ = ["BatchSizeTuner", "fit_linear", "powers_of_two"]


def fit_linear(xs: Sequence[float], ys: Sequence[float]
               ) -> tuple[float, float, float]:
    """Least-squares fit y = a + c*x. Returns (a, c, r_squared)."""
    if len(xs) != len(ys) or len(xs) < 3:
        raise TunerError("need >= 3 paired samples for a fit",
                         n=len(xs))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise TunerError("x samples have no variance")
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    c = sxy / sxx
    a = my - c * mx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy * sxy / (sxx * syy)) if syy > 0 else 0.0
    return a, c, r2


def powers_of_two(lo: int, hi: int) -> list[int]:
    """Powers of two in [lo, hi], plus the endpoints."""
    if lo > hi or lo < 1:
        raise TunerError("need 1 <= lo <= hi", lo=lo, hi=hi)
    out = {lo, hi}
    p = 1
    while p <= hi:
        if p >= lo:
            out.add(p)
        p *= 2
    return sorted(out)


@dataclass
class BatchSizeTuner(BaseTuner):
    """Pick the batch size maximizing fitted throughput under caps."""

    name: str = "batch_size_tuner"
    samples: Sequence[tuple[int, float, float]] = field(default_factory=list)
    latency_cap_ms: float = 100.0
    memory_cap_mb: float = 4096.0
    min_r_squared: float = 0.5

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("batch tuner needs a param name")
        if not self.objective_id:
            raise TunerError("batch tuner needs an objective_id")
        if len(self.samples) < 3:
            raise TunerError("need >= 3 samples", n=len(self.samples))
        for b, lat, mem in self.samples:
            if not isinstance(b, int) or isinstance(b, bool) or b < 1:
                raise TunerError("batch sizes must be positive ints")
            for v, name in ((lat, "latency"), (mem, "memory")):
                if not isinstance(v, (int, float)) or v < 0 \
                        or not math.isfinite(v):
                    raise TunerError(f"{name} samples must be finite >= 0")
        if self.latency_cap_ms <= 0 or self.memory_cap_mb <= 0:
            raise TunerError("caps must be positive")

    def _model(self) -> tuple[float, float, float, float, float, float]:
        bs = [float(b) for b, _, _ in self.samples]
        lats = [lat for _, lat, _ in self.samples]
        mems = [mem for _, _, mem in self.samples]
        a, c, r2_lat = fit_linear(bs, lats)
        m0, m1, r2_mem = fit_linear(bs, mems)
        return a, c, r2_lat, m0, m1, r2_mem

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "int":
            raise TunerError("batch tuner needs an int param",
                             param=self.param)
        a, c, r2_lat, m0, m1, r2_mem = self._model()
        if r2_lat < self.min_r_squared:
            return None  # model untrustworthy: stay silent
        cands = powers_of_two(int(param.lo), int(param.hi))  # type: ignore[arg-type]

        def latency_hat(b: int) -> float:
            return a + c * b

        def feasible(b: int) -> bool:
            return (latency_hat(b) <= self.latency_cap_ms
                    and m0 + m1 * b <= self.memory_cap_mb
                    and latency_hat(b) > 0)

        feas = [b for b in cands if feasible(b)]
        if not feas:
            return None
        best = max(feas, key=lambda b: b / latency_hat(b))
        current = int(ctx.store.get(self.param))
        base_thr = (current / latency_hat(current)
                    if feasible(current) else 0.0)
        best_thr = best / latency_hat(best)
        evidence: dict[str, Any] = {
            "latency_model": {"a_ms": a, "c_ms_per_item": c,
                              "r_squared": r2_lat},
            "memory_model": {"m0_mb": m0, "m1_mb_per_item": m1,
                             "r_squared": r2_mem},
            "latency_cap_ms": self.latency_cap_ms,
            "memory_cap_mb": self.memory_cap_mb,
            "baseline": {"batch_size": current,
                         "modeled_throughput": base_thr},
            "tuned": {"batch_size": best,
                      "modeled_throughput": best_thr},
            "candidates": feas,
        }
        return self._propose(ctx, {self.param: best}, base_thr, best_thr,
                             evidence)
