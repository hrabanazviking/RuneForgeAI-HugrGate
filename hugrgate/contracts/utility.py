"""Utility matrices — decisions as gains, not just losses.

Gjallarbrú slice 038.

Slice 037 prices mistakes (losses ≥ 0, minimized). The dual prices
*outcomes* (gains, possibly negative, maximized): a medical treatment
has benefit when right and harm when wrong; a bid has profit and loss.
This module adds:

- :class:`UtilityMatrix`: ``utility[decision][outcome]``, finite reals
  (negatives allowed), square over the outcome list;
- :func:`expected_utility` and :func:`max_utility_decision` (ties → outcome
  order);
- :class:`UtilityContract` (kind ``"utility"``): outcomes + matrix, with
  :meth:`decide`, :meth:`regret` (optimal EU − EU(chosen) ≥ 0), and
  :meth:`as_cost_matrix` — the duality bridge: ``C = max(U) − U`` is a
  valid cost matrix whose min-cost decision equals the max-utility one.

Utility and cost are two faces of one decision rule; the bridge is tested,
not just claimed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Tuple

from hugrgate.contracts.cost import CostMatrix
from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "UtilityMatrix",
    "UtilityContract",
    "expected_utility",
    "max_utility_decision",
]


def _check_outcomes(outcomes: Any) -> List[str]:
    if not isinstance(outcomes, list) or not outcomes:
        raise ContractError("utility matrix needs a non-empty outcomes list",
                            code="bad_outcomes")
    if len(set(outcomes)) != len(outcomes):
        raise ContractError("outcomes must be unique", code="bad_outcomes")
    if any(not isinstance(o, str) or not o for o in outcomes):
        raise ContractError("outcomes must be non-empty strings",
                            code="bad_outcomes")
    return list(outcomes)


def _check_finite(x: Any, *, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ContractError(f"{what} must be numeric, got {x!r}",
                            code="bad_utility")
    f = float(x)
    if not math.isfinite(f):
        raise ContractError(f"{what} must be finite, got {x!r}",
                            code="bad_utility")
    return f


class UtilityMatrix:
    """``utility[decision][outcome]`` — the gain of each pair."""

    __slots__ = ("_outcomes", "_utils")

    def __init__(self, outcomes: List[str],
                 utilities: Mapping[str, Mapping[str, float]]) -> None:
        self._outcomes = _check_outcomes(outcomes)
        if not isinstance(utilities, Mapping):
            raise ContractError("utilities must be a mapping",
                                code="bad_utilities")
        table: Dict[str, Dict[str, float]] = {}
        for dec in self._outcomes:
            if dec not in utilities:
                raise ContractError(f"utility matrix missing row: {dec!r}",
                                    code="bad_utilities")
            row = utilities[dec]
            if not isinstance(row, Mapping):
                raise ContractError(f"utility row {dec!r} must be a mapping",
                                    code="bad_utilities")
            missing = [o for o in self._outcomes if o not in row]
            if missing:
                raise ContractError(
                    f"utility row {dec!r} missing columns: {missing}",
                    code="bad_utilities")
            extra = [k for k in row if k not in self._outcomes]
            if extra:
                raise ContractError(
                    f"utility row {dec!r} has extra columns: {extra}",
                    code="bad_utilities")
            table[dec] = {o: _check_finite(row[o],
                                           what=f"utility[{dec!r}][{o!r}]")
                          for o in self._outcomes}
        self._utils = table

    @property
    def outcomes(self) -> Tuple[str, ...]:
        """Outcome labels in matrix order."""
        return tuple(self._outcomes)

    def utility(self, decision: str, outcome: str) -> float:
        """The gain of deciding ``decision`` when truth is ``outcome``."""
        try:
            return self._utils[decision][outcome]
        except KeyError:
            raise ContractError(
                f"unknown (decision, outcome) pair: {(decision, outcome)!r}",
                code="unknown_outcome") from None

    def row(self, decision: str) -> Dict[str, float]:
        """Copy of the utility row for one decision."""
        if decision not in self._utils:
            raise ContractError(f"unknown decision: {decision!r}",
                                code="unknown_outcome")
        return dict(self._utils[decision])

    def as_cost_matrix(self) -> CostMatrix:
        """Dual cost matrix: ``C = max(U) − U`` (all costs ≥ 0).

        Minimizing expected cost under ``C`` chooses the same label as
        maximizing expected utility under this matrix.
        """
        top = max(v for row in self._utils.values() for v in row.values())
        costs = {d: {o: top - u for o, u in row.items()}
                 for d, row in self._utils.items()}
        return CostMatrix(list(self._outcomes), costs)

    def to_dict(self) -> Dict[str, Any]:
        return {"outcomes": list(self._outcomes),
                "utilities": {d: dict(r)
                              for d, r in self._utils.items()}}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "UtilityMatrix":
        if not isinstance(d, Mapping):
            raise ContractError("utility matrix needs a mapping",
                                code="bad_utilities")
        try:
            return cls(outcomes=d["outcomes"], utilities=d["utilities"])
        except KeyError as e:
            raise ContractError(f"utility matrix missing key: {e}",
                                code="bad_utilities") from None

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, UtilityMatrix)
                and self._outcomes == other._outcomes
                and self._utils == other._utils)

    def __repr__(self) -> str:
        return f"UtilityMatrix(outcomes={self._outcomes!r})"


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
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ContractError(f"p({k!r}) must be numeric, got {v!r}",
                                code="bad_distribution")
        if not 0.0 <= v <= 1.0:
            raise ContractError(f"p({k!r}) outside [0,1]: {v}",
                                code="bad_distribution")
    total = sum(distribution.values())
    if abs(total - 1.0) > 1e-6:
        raise ContractError(f"distribution must sum to 1, got {total}",
                            code="bad_distribution")
    return {o: float(distribution.get(o, 0.0)) for o in outcomes}


def expected_utility(matrix: UtilityMatrix,
                     distribution: Mapping[str, float],
                     decision: str) -> float:
    """Σ_outcome p(outcome) · utility[decision][outcome]."""
    dist = _check_distribution(distribution, matrix.outcomes)
    row = matrix.row(decision)
    return sum(dist[o] * row[o] for o in matrix.outcomes)


def max_utility_decision(matrix: UtilityMatrix,
                         distribution: Mapping[str, float]
                         ) -> Tuple[str, float]:
    """The decision with maximum expected utility, and that utility.

    Deterministic tie-break: earliest in outcome order.
    """
    dist = _check_distribution(distribution, matrix.outcomes)
    best: str = matrix.outcomes[0]
    best_u = expected_utility(matrix, dist, best)
    for label in matrix.outcomes[1:]:
        u = expected_utility(matrix, dist, label)
        if u > best_u:
            best, best_u = label, u
    return best, best_u


@register_kind
@dataclass
class UtilityContract(DecisionContract):
    """Gain-maximizing decisions (kind ``"utility"``)."""

    kind: ClassVar[str] = "utility"

    outcomes: List[str] = field(default_factory=list)
    utilities: Dict[str, Dict[str, float]] = field(default_factory=dict)
    _matrix: UtilityMatrix = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        try:
            matrix = UtilityMatrix(self.outcomes, self.utilities)
        except ContractError as e:
            raise ContractError(f"invalid utility matrix: {e.message}",
                                code=e.details.get("code", "bad_utilities"))
        self._matrix = matrix
        self.outcomes = list(matrix.outcomes)
        self.utilities = matrix.to_dict()["utilities"]

    @property
    def matrix(self) -> UtilityMatrix:
        """The validated utility matrix."""
        return self._matrix

    def validate_value(self, value: Any) -> None:
        if value not in self._matrix.outcomes:
            raise ContractError(
                f"{value!r} not in outcomes {list(self._matrix.outcomes)}",
                code="value_outside_outcomes")

    def decide(self, distribution: Mapping[str, float]) -> Tuple[str, float]:
        """Maximum-expected-utility decision and its expected utility."""
        return max_utility_decision(self._matrix, distribution)

    def regret(self, distribution: Mapping[str, float],
               chosen: str) -> float:
        """Optimal EU minus EU(chosen) (≥ 0)."""
        _, best = self.decide(distribution)
        return best - expected_utility(self._matrix, distribution, chosen)

    def as_cost_matrix(self) -> CostMatrix:
        """This contract's dual cost matrix (slice 037)."""
        return self._matrix.as_cost_matrix()

    def _payload_dict(self) -> Dict[str, Any]:
        return {"outcomes": list(self._matrix.outcomes),
                "utilities": {d: dict(r) for d, r in
                              self._matrix.to_dict()["utilities"].items()}}

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: Dict[str, Any]) -> "UtilityContract":
        utilities = d.get("utilities")
        outcomes = d.get("outcomes")
        if not isinstance(utilities, dict) or not isinstance(outcomes, list):
            raise ContractError("utility payload needs 'outcomes' and "
                                "'utilities'", code="missing_utility_matrix")
        return cls(outcomes=outcomes, utilities=utilities, **common)

    def describe(self) -> str:
        n = len(self._matrix.outcomes)
        return (f"utility contract {self.name or self.contract_id!r}: "
                f"{n} outcomes, {n}×{n} utility matrix")
