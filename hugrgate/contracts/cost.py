"""Cost-sensitive decisions — when mistakes have different prices.

Gjallarbrú slice 037.

HugrGate policies maximize probability: the most likely outcome wins.
Reality prices mistakes differently — clearing a fraudulent transaction
costs far more than flagging a legitimate one. This module adds the
decision-theoretic core:

- :class:`CostMatrix`: ``cost[predicted][true]`` over an outcome list
  (non-negative; zero diagonal is conventional but not required — some
  domains charge even for correct-but-expensive actions);
- :func:`expected_cost` — Σ p(true) · cost[predicted][true];
- :func:`min_cost_decision` — the Bayes rule for costs: the label with
  minimum expected cost, which can *differ* from the most probable label;
- :class:`CostSensitiveContract` (kind ``"cost-sensitive"``): outcomes +
  cost matrix, with :meth:`decide` and :meth:`regret` (how much worse a
  chosen label is than optimal).

Slices 038 (utility) and 039 (risk) build on this foundation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Tuple

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "CostMatrix",
    "CostSensitiveContract",
    "expected_cost",
    "min_cost_decision",
]


def _check_outcomes(outcomes: Any) -> List[str]:
    if not isinstance(outcomes, list) or not outcomes:
        raise ContractError("cost matrix needs a non-empty outcomes list",
                            code="bad_outcomes")
    if len(set(outcomes)) != len(outcomes):
        raise ContractError("outcomes must be unique", code="bad_outcomes")
    if any(not isinstance(o, str) or not o for o in outcomes):
        raise ContractError("outcomes must be non-empty strings",
                            code="bad_outcomes")
    return list(outcomes)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class CostMatrix:
    """``cost[predicted][true]`` — the price of each (decision, truth) pair."""

    __slots__ = ("_outcomes", "_costs")

    def __init__(self, outcomes: List[str],
                 costs: Mapping[str, Mapping[str, float]]) -> None:
        self._outcomes = _check_outcomes(outcomes)
        if not isinstance(costs, Mapping):
            raise ContractError("costs must be a mapping",
                                code="bad_costs")
        missing_rows = [o for o in self._outcomes if o not in costs]
        if missing_rows:
            raise ContractError(f"cost matrix missing rows: {missing_rows}",
                                code="bad_costs")
        extra_rows = [k for k in costs if k not in self._outcomes]
        if extra_rows:
            raise ContractError(f"cost matrix has extra rows: {extra_rows}",
                                code="bad_costs")
        table: Dict[str, Dict[str, float]] = {}
        for pred in self._outcomes:
            row = costs[pred]
            if not isinstance(row, Mapping):
                raise ContractError(f"cost row {pred!r} must be a mapping",
                                    code="bad_costs")
            missing = [o for o in self._outcomes if o not in row]
            if missing:
                raise ContractError(
                    f"cost row {pred!r} missing columns: {missing}",
                    code="bad_costs")
            extra = [k for k in row if k not in self._outcomes]
            if extra:
                raise ContractError(
                    f"cost row {pred!r} has extra columns: {extra}",
                    code="bad_costs")
            clean_row = {}
            for true in self._outcomes:
                c = row[true]
                if not _is_num(c) or c < 0:
                    raise ContractError(
                        f"cost[{pred!r}][{true!r}] must be ≥ 0, got {c!r}",
                        code="bad_costs")
                clean_row[true] = float(c)
            table[pred] = clean_row
        self._costs = table

    @property
    def outcomes(self) -> Tuple[str, ...]:
        """Outcome labels in matrix order."""
        return tuple(self._outcomes)

    def cost(self, predicted: str, true: str) -> float:
        """The price of deciding ``predicted`` when truth is ``true``."""
        try:
            return self._costs[predicted][true]
        except KeyError:
            raise ContractError(
                f"unknown (predicted, true) pair: {(predicted, true)!r}",
                code="unknown_outcome") from None

    def row(self, predicted: str) -> Dict[str, float]:
        """Copy of the cost row for one predicted label."""
        if predicted not in self._costs:
            raise ContractError(f"unknown predicted label: {predicted!r}",
                                code="unknown_outcome")
        return dict(self._costs[predicted])

    def to_dict(self) -> Dict[str, Any]:
        return {"outcomes": list(self._outcomes),
                "costs": {p: dict(r) for p, r in self._costs.items()}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "CostMatrix":
        if not isinstance(d, Mapping):
            raise ContractError("cost matrix needs a mapping",
                                code="bad_costs")
        try:
            return cls(outcomes=d["outcomes"], costs=d["costs"])
        except KeyError as e:
            raise ContractError(f"cost matrix missing key: {e}",
                                code="bad_costs") from None

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, CostMatrix)
                and self._outcomes == other._outcomes
                and self._costs == other._costs)

    def __repr__(self) -> str:
        return f"CostMatrix(outcomes={self._outcomes!r})"


def _check_distribution(distribution: Any,
                        outcomes: Tuple[str, ...]) -> Dict[str, float]:
    if not isinstance(distribution, Mapping) or not distribution:
        raise ContractError("distribution must be a non-empty mapping",
                            code="bad_distribution")
    bad = [k for k in distribution if k not in outcomes]
    if bad:
        raise ContractError(f"distribution keys outside outcomes: {bad}",
                            code="distribution_key_outside_outcomes")
    for k, v in distribution.items():
        if not _is_num(v) or not 0.0 <= v <= 1.0:
            raise ContractError(f"p({k!r}) must be in [0,1], got {v!r}",
                                code="bad_distribution")
    total = sum(distribution.values())
    if abs(total - 1.0) > 1e-6:
        raise ContractError(f"distribution must sum to 1, got {total}",
                            code="bad_distribution")
    return {o: float(distribution.get(o, 0.0)) for o in outcomes}


def expected_cost(matrix: CostMatrix, distribution: Mapping[str, float],
                  predicted: str) -> float:
    """Σ_true p(true) · cost[predicted][true]."""
    dist = _check_distribution(distribution, matrix.outcomes)
    row = matrix.row(predicted)
    return sum(dist[true] * row[true] for true in matrix.outcomes)


def min_cost_decision(matrix: CostMatrix,
                      distribution: Mapping[str, float]
                      ) -> Tuple[str, float]:
    """The label with minimum expected cost, and that cost.

    Deterministic tie-break: earliest in outcome order.
    """
    dist = _check_distribution(distribution, matrix.outcomes)
    best: str = matrix.outcomes[0]
    best_cost = expected_cost(matrix, dist, best)
    for label in matrix.outcomes[1:]:
        c = expected_cost(matrix, dist, label)
        if c < best_cost:
            best, best_cost = label, c
    return best, best_cost


@register_kind
@dataclass
class CostSensitiveContract(DecisionContract):
    """Decisions priced by a cost matrix (kind ``"cost-sensitive"``)."""

    kind: ClassVar[str] = "cost-sensitive"

    outcomes: List[str] = field(default_factory=list)
    costs: Dict[str, Dict[str, float]] = field(default_factory=dict)
    _matrix: CostMatrix = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        try:
            matrix = CostMatrix(self.outcomes, self.costs)
        except ContractError as e:
            raise ContractError(f"invalid cost matrix: {e.message}",
                                code=e.details.get("code", "bad_costs"))
        self._matrix = matrix
        # Normalize stored form through the matrix (ordering, float casts).
        self.outcomes = list(matrix.outcomes)
        self.costs = matrix.to_dict()["costs"]

    @property
    def matrix(self) -> CostMatrix:
        """The validated cost matrix."""
        return self._matrix

    def validate_value(self, value: Any) -> None:
        if value not in self._matrix.outcomes:
            raise ContractError(
                f"{value!r} not in outcomes {list(self._matrix.outcomes)}",
                code="value_outside_outcomes")

    def decide(self, distribution: Mapping[str, float]) -> Tuple[str, float]:
        """Minimum-expected-cost label and its expected cost."""
        return min_cost_decision(self._matrix, distribution)

    def regret(self, distribution: Mapping[str, float],
               chosen: str) -> float:
        """Expected cost of ``chosen`` minus the optimal expected cost (≥0)."""
        _, best = self.decide(distribution)
        return expected_cost(self._matrix, distribution, chosen) - best

    def _payload_dict(self) -> Dict[str, Any]:
        return {"outcomes": list(self._matrix.outcomes),
                "costs": {p: dict(r)
                          for p, r in self._matrix.to_dict()["costs"].items()}}

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "CostSensitiveContract":
        costs = d.get("costs")
        outcomes = d.get("outcomes")
        if not isinstance(costs, dict) or not isinstance(outcomes, list):
            raise ContractError("cost-sensitive payload needs 'outcomes' "
                                "and 'costs'", code="missing_cost_matrix")
        return cls(outcomes=outcomes, costs=costs, **common)

    def describe(self) -> str:
        n = len(self._matrix.outcomes)
        return (f"cost-sensitive contract {self.name or self.contract_id!r}: "
                f"{n} outcomes, {n}×{n} cost matrix")
