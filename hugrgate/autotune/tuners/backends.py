"""Backend-order tuner. Slice 459.

When the primary backend fails or abstains, HugrGate falls through to
the next backend. The try-order decides the expected cost:

    E[cost] = c_1 + f_1·c_2 + f_1·f_2·c_3 + …

where c_i is the per-call cost and f_i the failure probability. The
optimal order is *not* "cheapest first": by the pairwise interchange
argument, adjacent backends i, j should be swapped exactly when
``c_i/s_i > c_j/s_j`` (s = success probability), i.e. the optimal
order sorts by **cost-per-success ascending** (Smith's rule for
fallthrough chains).

This tuner computes that order from measured (success_rate, cost)
pairs and proposes rank assignments for one int param per backend
(``{rank_prefix}.{name}`` in [0, K-1]); consumers sort by rank.
The test suite verifies the tuner's order against brute-force
permutation search on randomized instances.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.errors import TunerError

__all__ = ["BackendOrderTuner", "expected_chain_cost"]


def expected_chain_cost(order: Sequence[str],
                        stats: Mapping[str, tuple[float, float]]) -> float:
    """Expected fallthrough cost for an order.

    ``stats[name]`` = (success_rate, cost_per_call).
    """
    total = 0.0
    reach = 1.0
    for name in order:
        s, c = stats[name]
        total += reach * c
        reach *= 1.0 - s
    return total


@dataclass
class BackendOrderTuner(BaseTuner):
    """Reorder the backend fallthrough chain by cost-per-success."""

    name: str = "backend_order_tuner"
    backends: Sequence[str] = field(default_factory=list)
    stats: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rank_prefix: str = "backend.rank"

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise TunerError("backend tuner needs an objective_id")
        if len(self.backends) < 2:
            raise TunerError("need at least 2 backends")
        if len(set(self.backends)) != len(self.backends):
            raise TunerError("duplicate backend names")
        if set(self.stats) != set(self.backends):
            raise TunerError("stats must cover exactly the backends")
        for b in self.backends:
            s, c = self.stats[b]
            if not 0.0 < s <= 1.0:
                raise TunerError("success_rate must be in (0, 1]",
                                 backend=b)
            if not math.isfinite(c) or c < 0:
                raise TunerError("cost must be finite >= 0", backend=b)
        if not self.rank_prefix:
            raise TunerError("rank_prefix must be non-empty")

    def _param(self, backend: str) -> str:
        return f"{self.rank_prefix}.{backend}"

    def _optimal_order(self) -> list[str]:
        # Sort by cost/success ascending; ties broken by name for
        # determinism.
        return sorted(self.backends,
                      key=lambda b: (self.stats[b][1] / self.stats[b][0], b))

    def _current_order(self, ctx: TuningContext) -> list[str]:
        ranks = {}
        for b in self.backends:
            param = ctx.store.describe(self._param(b))
            if param.dtype != "int":
                raise TunerError("rank params must be int",
                                 param=self._param(b))
            ranks[b] = int(ctx.store.get(self._param(b)))
        return sorted(self.backends, key=lambda b: (ranks[b], b))

    def tune(self, ctx: TuningContext) -> Proposal | None:
        order = self._optimal_order()
        current = self._current_order(ctx)
        base_cost = expected_chain_cost(current, self.stats)
        best_cost = expected_chain_cost(order, self.stats)
        changes = {self._param(b): rank for rank, b in enumerate(order)}
        evidence: dict[str, Any] = {
            "cost_per_success": {b: self.stats[b][1] / self.stats[b][0]
                                 for b in self.backends},
            "baseline": {"order": current,
                         "expected_cost": base_cost},
            "tuned": {"order": order, "expected_cost": best_cost},
            "optimality": ("pairwise interchange: adjacent i,j improve "
                           "iff c_i/s_i > c_j/s_j, so sorting by "
                           "cost/success ascending is optimal"),
        }
        # Negated cost: higher is better.
        return self._propose(ctx, changes, -base_cost, -best_cost,
                             evidence)
