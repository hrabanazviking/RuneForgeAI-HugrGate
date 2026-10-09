"""Cost-aware evaluation — decision quality per unit spend. Slice 363.

The cost cascade per backend mirrors :mod:`hugrgate.routing.cost`'s
actuals-first rule:

1. ``result.metadata["cost"]`` summed over decisions (true spend
   reported by the backend itself);
2. ``backend.estimated_cost()`` * n_decisions (declared estimate);
3. :class:`CostModel` per-backend rates (lab fallback).

The :class:`CostReport` carries per-backend efficiency metrics
(accuracy per cost, cost per correct decision), the Pareto frontier
(max accuracy at min cost — no backend on it is strictly worse on
both axes), and budget-constrained queries
(:meth:`CostReport.best_under_budget`,
:meth:`CostReport.cheapest_at_accuracy`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate import bench as _bench
from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "CostModel",
    "CostReport",
    "cost_aware_evaluate",
    "pareto_frontier",
]


@dataclass
class CostModel:
    """Lab fallback rates: cost per decision by backend name."""

    rates: dict[str, float] = field(default_factory=dict)
    default_rate: float = 0.0
    currency: str = "USD"

    def rate_for(self, backend: str) -> float:
        rate = self.rates.get(backend, self.default_rate)
        if rate < 0:
            raise EvalError(
                f"negative cost rate for backend {backend!r}: {rate}"
            )
        return rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "rates": dict(self.rates),
            "default_rate": self.default_rate,
            "currency": self.currency,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CostModel:
        return cls(
            rates=dict(data.get("rates", {})),
            default_rate=data.get("default_rate", 0.0),
            currency=data.get("currency", "USD"),
        )


def _evaluate_costs(
    gate: HugrGate,
    dataset: Mapping[str, Any],
    backend_name: str,
    policy: DecisionPolicy,
    max_items: int | None,
    model: CostModel,
) -> dict[str, Any]:
    """Evaluate once; return pairs, accuracy, total cost + its source."""
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    pairs: list[tuple[Any, DecisionResult]] = []
    actual_costs: list[float] = []
    for item in items:
        expected = item.get("expected")
        try:
            result = gate.decide(dict(item["state"]), spec, policy,
                                 backend_name=backend_name)
        except Abstention:
            continue
        pairs.append((expected, result))
        reported = result.metadata.get("cost")
        if isinstance(reported, (int, float)) and reported >= 0:
            actual_costs.append(float(reported))
    accuracy = _bench.accuracy(pairs)
    n = len(pairs)
    backend_obj = gate.registry.get(backend_name)
    if actual_costs and len(actual_costs) == n:
        # Every decision reported true spend: trust it.
        return {"pairs": pairs, "accuracy": accuracy, "n": n,
                "total_cost": sum(actual_costs), "cost_source": "actual"}
    declared = backend_obj.estimated_cost() if backend_obj else 0.0
    if declared > 0:
        return {"pairs": pairs, "accuracy": accuracy, "n": n,
                "total_cost": declared * n, "cost_source": "estimated"}
    rate = model.rate_for(backend_name)
    return {"pairs": pairs, "accuracy": accuracy, "n": n,
            "total_cost": rate * n, "cost_source": "model"}


def pareto_frontier(
    points: Mapping[str, tuple[float, float]],
) -> list[str]:
    """Names on the Pareto frontier of (cost, accuracy) points.

    A point is dominated when another has ``cost <=`` and
    ``accuracy >=`` with at least one strict inequality.
    """
    names = list(points)
    frontier = []
    for name in names:
        cost, acc = points[name]
        dominated = any(
            other != name
            and points[other][0] <= cost
            and points[other][1] >= acc
            and (points[other][0] < cost or points[other][1] > acc)
            for other in names
        )
        if not dominated:
            frontier.append(name)
    return sorted(frontier)


@dataclass
class CostReport:
    """Per-backend cost/quality results + frontier (slice 363)."""

    backends: dict[str, dict[str, Any]]
    pareto: list[str]
    currency: str
    n_items: int

    def best_under_budget(
        self, budget: float
    ) -> tuple[str | None, float | None]:
        """(backend, accuracy) maximizing accuracy within ``budget``."""
        if budget < 0:
            raise EvalError(f"budget must be >= 0, got {budget}")
        candidates = [
            (name, info["accuracy"])
            for name, info in self.backends.items()
            if info["total_cost"] <= budget
            and isinstance(info["accuracy"], (int, float))
        ]
        if not candidates:
            return None, None
        return max(candidates, key=lambda kv: kv[1])

    def cheapest_at_accuracy(
        self, min_accuracy: float
    ) -> tuple[str | None, float | None]:
        """(backend, total_cost) minimizing cost at ``min_accuracy``."""
        if not 0.0 <= min_accuracy <= 1.0:
            raise EvalError(
                f"min_accuracy must be in [0, 1], got {min_accuracy}"
            )
        candidates = [
            (name, info["total_cost"])
            for name, info in self.backends.items()
            if isinstance(info["accuracy"], (int, float))
            and info["accuracy"] >= min_accuracy
        ]
        if not candidates:
            return None, None
        return min(candidates, key=lambda kv: kv[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "backends": {b: dict(info)
                         for b, info in self.backends.items()},
            "pareto": list(self.pareto),
            "currency": self.currency,
            "n_items": self.n_items,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CostReport:
        return cls(
            backends={b: dict(info)
                      for b, info in data["backends"].items()},
            pareto=list(data["pareto"]),
            currency=data.get("currency", "USD"),
            n_items=data["n_items"],
        )


def cost_aware_evaluate(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backends: Sequence[str] | None = None,
    cost_model: CostModel | None = None,
    policy: DecisionPolicy | None = None,
    max_items: int | None = None,
) -> CostReport:
    """Evaluate backends for quality *and* spend; return a CostReport."""
    model = cost_model or CostModel()
    policy = policy or DecisionPolicy()
    spec = DecisionSpec.from_dict(dataset["spec"])
    names = list(backends) if backends is not None \
        else [b.name for b in gate.registry.supporting(spec)]
    if not names:
        raise EvalError("no backends available for this dataset's spec")

    results: dict[str, dict[str, Any]] = {}
    n_items = 0
    for backend in names:
        ev = _evaluate_costs(gate, dataset, backend, policy, max_items,
                            model)
        n_items = max(n_items, len(list(dataset.get("items", []))))
        accuracy = ev["accuracy"]
        total_cost = ev["total_cost"]
        n_correct = (
            round(accuracy * ev["n"]) if accuracy is not None else 0
        )
        results[backend] = {
            "accuracy": accuracy,
            "n_decided": ev["n"],
            "total_cost": total_cost,
            "cost_source": ev["cost_source"],
            "accuracy_per_cost": (
                accuracy / total_cost
                if accuracy is not None and total_cost > 0 else None
            ),
            "cost_per_correct": (
                total_cost / n_correct if n_correct > 0 else None
            ),
        }
    frontier = pareto_frontier({
        name: (info["total_cost"], info["accuracy"] or 0.0)
        for name, info in results.items()
    })
    return CostReport(backends=results, pareto=frontier,
                      currency=model.currency, n_items=n_items)
