"""Node cost scoring. Slice 215.

Some peers charge for inference (credits, dollars, energy — the unit
is the operator's; this module only compares). Two mechanisms:

1. **Scoring** — ``score = 1 / (1 + cost)``: a free peer scores 1.0,
   cost 1 scores 0.5, cost 9 scores 0.1. Diminishing, so cost is a
   preference, not a veto.

2. **Budget filtering** — a *veto*: when ``DecisionPolicy.max_cost``
   is set, any peer whose cost per decision exceeds it is excluded
   from routing entirely (the router's ``_peer_allowed`` enforces
   this). Fail-closed on budgets: a peer with unknown cost is treated
   as free (0.0), never excluded — exclusion requires evidence.

Costs are operator-set per peer (static config, slice 205) and reset
when a peer rejoins clean (slice 220).
"""

from __future__ import annotations

import math
import threading

from hugrgate.errors import SpecError

__all__ = [
    "CostModel",
]


class CostModel:
    """Per-peer cost per decision. Thread-safe."""

    def __init__(self) -> None:
        self._costs: dict[str, float] = {}
        self._lock = threading.RLock()

    def set_cost(self, node_id: str, cost_per_decision: float) -> None:
        """Set what one remote decision on this peer costs."""
        if (not isinstance(cost_per_decision, (int, float))
                or not math.isfinite(cost_per_decision)
                or cost_per_decision < 0):
            raise SpecError(
                "cost_per_decision must be a non-negative finite "
                f"number, got {cost_per_decision!r}")
        with self._lock:
            self._costs[node_id] = float(cost_per_decision)

    def cost_of(self, node_id: str) -> float:
        """Cost per decision; 0.0 when unknown (treated as free)."""
        with self._lock:
            return self._costs.get(node_id, 0.0)

    def score(self, node_id: str) -> float:
        """Cost score in [0, 1]: ``1 / (1 + cost)``."""
        with self._lock:
            cost = self._costs.get(node_id, 0.0)
        return 1.0 / (1.0 + cost)

    def affordable(self, node_id: str,
                   max_cost: float | None) -> bool:
        """True when this peer fits inside the budget."""
        if max_cost is None:
            return True
        return self.cost_of(node_id) <= max_cost

    def reset(self, node_id: str) -> None:
        with self._lock:
            self._costs.pop(node_id, None)
