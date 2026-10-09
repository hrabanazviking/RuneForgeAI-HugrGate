"""Cache-policy tuner. Slice 457.

Attacks a real weakness: :class:`hugrgate.cache.DecisionCache` ships
with hand-picked ``ttl_seconds`` / ``max_size`` and a fixed LRU
discipline. This tuner replays a recorded access trace through a
simulator over a grid of (ttl, max_size, eviction) candidates and
proposes the cheapest configuration — measured, not guessed.

The simulator is deliberately simple and documented as such: it
models insert/access/expiry/eviction on (key, timestamp, miss_cost)
triples. It does not model DecisionCache's policy-fingerprint
namespacing; it answers "which (ttl, size, eviction) wastes the least
miss cost on *this* trace", which is exactly the question a cache
tuner should answer.

Candidates: ttl on a linear grid inside the param bounds, max_size on
a geometric ladder clipped to the param bounds, eviction over the
param's declared choices (subset of {"lru", "lfu"}).
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner, linspace
from hugrgate.errors import TunerError

__all__ = ["CachePolicyTuner", "simulate_trace"]

TraceEvent = tuple[Hashable, float, float]  # (key, timestamp, miss_cost)


def simulate_trace(trace: Sequence[TraceEvent], ttl: float,
                   max_size: int, eviction: str) -> dict[str, float]:
    """Replay a trace; return hit_rate, total_cost, hits, misses."""
    if eviction not in ("lru", "lfu"):
        raise TunerError("eviction must be lru/lfu", eviction=eviction)
    if max_size < 1:
        raise TunerError("max_size must be >= 1", max_size=max_size)
    # key -> [inserted_at, last_access, frequency]
    cache: dict[Hashable, list[float]] = {}
    hits = 0
    misses = 0
    total_cost = 0.0
    for key, ts, miss_cost in trace:
        entry = cache.get(key)
        if entry is not None and ts - entry[0] <= ttl:
            hits += 1
            entry[1] = ts
            entry[2] += 1.0
            continue
        # miss (absent or expired)
        if entry is not None:
            del cache[key]
        misses += 1
        total_cost += miss_cost
        if len(cache) >= max_size:
            if eviction == "lru":
                victim = min(cache, key=lambda k: cache[k][1])
            else:
                victim = min(cache, key=lambda k: (cache[k][2], cache[k][1]))
            del cache[victim]
        cache[key] = [ts, ts, 1.0]
    n = hits + misses
    return {"hit_rate": hits / n if n else 0.0,
            "total_cost": total_cost,
            "hits": float(hits), "misses": float(misses)}


@dataclass
class CachePolicyTuner(BaseTuner):
    """Choose (ttl, max_size, eviction) by trace replay."""

    name: str = "cache_policy_tuner"
    ttl_param: str = ""
    size_param: str = ""
    eviction_param: str = ""
    trace: Sequence[TraceEvent] = field(default_factory=list)
    ttl_grid: int = 9
    size_ladder: Sequence[int] = (32, 128, 512, 2048, 8192)

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise TunerError("cache tuner needs an objective_id")
        if not (self.ttl_param and self.size_param and self.eviction_param):
            raise TunerError("cache tuner needs ttl/size/eviction params")
        if len(self.trace) < 20:
            raise TunerError("trace too short", n=len(self.trace))
        for _key, ts, cost in self.trace:
            if not isinstance(ts, (int, float)) or not math.isfinite(ts):
                raise TunerError("trace timestamps must be finite")
            if not isinstance(cost, (int, float)) or cost < 0 \
                    or not math.isfinite(cost):
                raise TunerError("miss costs must be finite >= 0")

    def _candidates(self, ctx: TuningContext
                    ) -> tuple[list[float], list[int], list[str]]:
        ttl_p = ctx.store.describe(self.ttl_param)
        size_p = ctx.store.describe(self.size_param)
        ev_p = ctx.store.describe(self.eviction_param)
        if ttl_p.dtype != "float" or size_p.dtype != "int" \
                or ev_p.dtype != "str":
            raise TunerError("cache tuner needs float/int/str params")
        ttls = linspace(float(ttl_p.lo), float(ttl_p.hi),  # type: ignore[arg-type]
                        self.ttl_grid)
        sizes = sorted({s for s in self.size_ladder
                        if size_p.lo <= s <= size_p.hi})  # type: ignore[operator]
        if not sizes:
            # ladder misses the bounds: fall back to the bound endpoints
            sizes = sorted({int(size_p.lo), int(size_p.hi)})  # type: ignore[arg-type]
        evictions = [e for e in (ev_p.choices or ()) if e in ("lru", "lfu")]
        if not evictions:
            raise TunerError("eviction param must offer lru and/or lfu",
                             choices=ev_p.choices)
        return ttls, sizes, evictions

    def tune(self, ctx: TuningContext) -> Proposal | None:
        ttls, sizes, evictions = self._candidates(ctx)
        best: tuple[float, float, int, str] | None = None  # cost, ttl, size, ev
        for ttl in ttls:
            for size in sizes:
                for ev in evictions:
                    res = simulate_trace(self.trace, ttl, size, ev)
                    cand = (res["total_cost"], ttl, size, ev)
                    if best is None or cand < best:
                        best = cand
        assert best is not None
        best_cost, best_ttl, best_size, best_ev = best
        cur_ttl = float(ctx.store.get(self.ttl_param))
        cur_size = int(ctx.store.get(self.size_param))
        cur_ev = str(ctx.store.get(self.eviction_param))
        cur = {self.ttl_param: cur_ttl, self.size_param: cur_size,
               self.eviction_param: cur_ev}
        if cur_ev not in ("lru", "lfu"):
            raise TunerError("current eviction value not simulatable",
                             value=cur_ev)
        base = simulate_trace(self.trace, cur_ttl, cur_size, cur_ev)
        changes = {self.ttl_param: best_ttl, self.size_param: best_size,
                   self.eviction_param: best_ev}
        evidence: dict[str, Any] = {
            "trace_events": len(self.trace),
            "candidates_evaluated": len(ttls) * len(sizes) * len(evictions),
            "baseline": {"config": cur, **base},
            "tuned": {"config": changes, "total_cost": best_cost,
                      "hit_rate": simulate_trace(
                          self.trace, best_ttl, best_size,
                          best_ev)["hit_rate"]},
            "note": "simulator models insert/access/expiry/eviction only; "
                    "it does not model policy-fingerprint namespacing",
        }
        # Negated cost so higher is better.
        return self._propose(ctx, changes, -base["total_cost"], -best_cost,
                             evidence)
