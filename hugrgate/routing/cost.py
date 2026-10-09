"""Cost-aware routing. Slice 057.

Money is a routing constraint like latency: :class:`CostLedger` holds a
per-request spend budget — ``options.max_cost`` when set, else the
policy's ``max_cost`` — and tracks reservations (plan time) and actuals
(run time). :class:`CostAwarePlanner` prunes rungs the budget cannot
cover before execution, spending the budget cumulatively down the plan so
a ladder of individually-cheap rungs cannot silently exceed it.

Actuals come from ``result.metadata["cost"]`` when a backend reports its
true spend, else fall back to ``backend.estimated_cost()``. The router
feeds them back via ``LadderRouterV2.note_cost`` after each climb, the
same pattern slice 056 established for latency.
"""

from __future__ import annotations

from hugrgate.routing.architecture import (
    RouterContext,
    RoutingPlan,
    RungNode,
    RungPlanner,
)

__all__ = [
    "CostAwarePlanner",
    "CostLedger",
    "budget_for",
]


def budget_for(ctx: RouterContext) -> float | None:
    """Effective per-request cost budget: options override policy."""
    if ctx.options.max_cost is not None:
        return ctx.options.max_cost
    return ctx.policy.max_cost


class CostLedger:
    """Per-request cost accounting: reserve at plan time, spend at run time."""

    def __init__(self, budget: float | None):
        if budget is not None and budget < 0:
            raise ValueError(f"budget must be non-negative, got {budget}")
        self.budget = budget
        self.reserved = 0.0
        self.spent = 0.0
        self.entries: list[dict] = []

    @property
    def remaining(self) -> float | None:
        if self.budget is None:
            return None
        return max(0.0, self.budget - self.reserved - self.spent)

    def can_afford(self, estimate: float) -> bool:
        """True when the estimate fits the uncommitted budget (or unbounded)."""
        remaining = self.remaining
        if remaining is None:
            return True
        return estimate <= remaining

    def reserve(self, backend_name: str, estimate: float) -> bool:
        """Reserve budget for a planned rung; False when unaffordable."""
        if not self.can_afford(estimate):
            return False
        self.reserved += estimate
        self.entries.append({"backend": backend_name, "reserved": estimate})
        return True

    def spend(self, backend_name: str, actual: float) -> None:
        if actual < 0:
            raise ValueError(f"actual cost must be non-negative, got {actual}")
        self.spent += actual
        self.entries.append({"backend": backend_name, "spent": actual})

    def to_dict(self) -> dict:
        return {
            "budget": self.budget,
            "reserved": round(self.reserved, 6),
            "spent": round(self.spent, 6),
            "remaining": (round(self.remaining, 6)
                          if self.remaining is not None else None),
            "entries": list(self.entries),
        }


class CostAwarePlanner(RungPlanner):
    """Wrap a planner; prune rungs the cost budget cannot cover.

    Walks the inner plan top-down, reserving each rung's estimated cost
    against the ledger. A rung that does not fit the remaining budget is
    pruned with its cost recorded in the rationale. Surviving nodes carry
    ``params["cost_estimate"]``. The executor still re-checks affordability
    at run time via ``router.cost_ledger``.
    """

    def __init__(self, inner: RungPlanner, registry,
                 ledger: CostLedger | None = None):
        self.inner = inner
        self.registry = registry
        self.ledger = ledger  # may be replaced per request in plan()

    def plan(self, ctx: RouterContext) -> RoutingPlan:
        plan = self.inner.plan(ctx)
        ledger = self.ledger or CostLedger(budget_for(ctx))
        kept: list[RungNode] = []
        pruned: list[str] = []
        for node in plan.nodes:
            backend = self.registry.get(node.backend_name)
            estimate = (backend.estimated_cost()
                        if backend is not None else 0.0)
            node.params["cost_estimate"] = estimate
            if ledger.reserve(node.backend_name, estimate):
                kept.append(node)
            else:
                pruned.append(
                    f"{node.backend_name}: est. cost {estimate:.4f} "
                    f"exceeds remaining budget "
                    f"{ledger.remaining:.4f}")
        plan.nodes = kept
        plan.created_by = f"{plan.created_by}+cost"
        plan.rationale.append(
            f"cost ledger: budget={ledger.budget}, "
            f"reserved={ledger.reserved:.4f}, "
            f"pruned {len(pruned)} rung(s)"
            + (": " + "; ".join(pruned) if pruned else ""))
        plan.ledger = ledger  # type: ignore[attr-defined]
        return plan
