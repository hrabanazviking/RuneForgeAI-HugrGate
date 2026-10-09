"""Risk matrices — deciding under risk aversion. Gjallarbrú slice 039.

Slices 037-038 optimize *expectation*: minimum expected cost, maximum
expected utility. A risk-averse decision maker cares about the *worst
case*, not the average. This module reuses :class:`CostMatrix` as the
loss matrix (law 2: reuse sound architecture) and adds three
risk-sensitive decision rules:

- :func:`minimax_decision` — minimize the worst-case loss. Needs no
  distribution: pure robustness;
- :func:`minimax_regret_decision` — minimize the worst-case *regret*,
  where ``regret[d][o] = loss[d][o] - min_d' loss[d'][o]``;
- :func:`cvar_decision` — minimize CVaR_alpha: the expected loss in the
  worst (1-alpha) tail of the loss distribution (alpha=0 recovers expectation).

:class:`RiskContract` (kind ``"risk"``) binds outcomes + loss matrix +
``attitude`` (``minimax`` | ``minimax_regret`` | ``cvar``) with
``cvar_alpha`` for the tail rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.contracts.cost import CostMatrix, expected_cost
from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "RISK_ATTITUDES",
    "RiskContract",
    "cvar_decision",
    "cvar_of_decision",
    "minimax_decision",
    "minimax_regret_decision",
    "regret_table",
]

#: Risk attitudes a RiskContract can take.
RISK_ATTITUDES = ("minimax", "minimax_regret", "cvar")


def _check_distribution(distribution: Any,
                        outcomes: tuple[str, ...]) -> dict[str, float]:
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


def minimax_decision(matrix: CostMatrix) -> tuple[str, float]:
    """Label minimizing worst-case loss; returns (label, worst-case loss).

    Distribution-free: pure robustness. Ties → outcome order.
    """
    best, best_worst = matrix.outcomes[0], 0.0
    first = True
    for dec in matrix.outcomes:
        worst = max(matrix.row(dec).values())
        if first or worst < best_worst:
            best, best_worst, first = dec, worst, False
    return best, best_worst


def regret_table(matrix: CostMatrix) -> dict[str, dict[str, float]]:
    """``regret[d][o] = loss[d][o] - min_d' loss[d'][o]`` (all ≥ 0)."""
    outcomes = matrix.outcomes
    best_loss = {o: min(matrix.cost(d, o) for d in outcomes)
                 for o in outcomes}
    return {d: {o: matrix.cost(d, o) - best_loss[o] for o in outcomes}
            for d in outcomes}


def minimax_regret_decision(matrix: CostMatrix) -> tuple[str, float]:
    """Label minimizing worst-case regret; returns (label, max regret)."""
    table = regret_table(matrix)
    best, best_worst = matrix.outcomes[0], 0.0
    first = True
    for dec in matrix.outcomes:
        worst = max(table[dec].values())
        if first or worst < best_worst:
            best, best_worst, first = dec, worst, False
    return best, best_worst


def cvar_of_decision(matrix: CostMatrix,
                     distribution: Mapping[str, float],
                     decision: str, alpha: float) -> float:
    """CVaR_alpha of the loss distribution for ``decision``.

    Sort outcomes by loss descending, walk the worst outcomes until
    (1-alpha) mass is covered (splitting the boundary outcome), and average.
    alpha=0 recovers the expected loss.
    """
    if not 0.0 <= alpha < 1.0:
        raise ContractError(f"cvar alpha must be in [0, 1), got {alpha}",
                            code="bad_cvar_alpha")
    dist = _check_distribution(distribution, matrix.outcomes)
    row = matrix.row(decision)  # validates the decision label
    pairs = sorted(((row[o], dist[o]) for o in matrix.outcomes),
                   reverse=True)
    tail_mass = 1.0 - alpha
    if tail_mass <= 0.0:
        return max(row.values())
    acc, acc_mass = 0.0, 0.0
    for loss, p in pairs:
        if acc_mass >= tail_mass or p <= 0.0:
            continue
        take = min(p, tail_mass - acc_mass)
        acc += take * loss
        acc_mass += take
    if acc_mass <= 0.0:
        return 0.0
    return acc / acc_mass


def cvar_decision(matrix: CostMatrix,
                  distribution: Mapping[str, float],
                  alpha: float = 0.9) -> tuple[str, float]:
    """Label minimizing CVaR_alpha; returns (label, cvar). Ties → outcome order."""
    best, best_cvar = matrix.outcomes[0], 0.0
    first = True
    for dec in matrix.outcomes:
        c = cvar_of_decision(matrix, distribution, dec, alpha)
        if first or c < best_cvar:
            best, best_cvar, first = dec, c, False
    return best, best_cvar


@register_kind
@dataclass
class RiskContract(DecisionContract):
    """Risk-averse decisions over a loss matrix (kind ``"risk"``)."""

    kind: ClassVar[str] = "risk"

    outcomes: list[str] = field(default_factory=list)
    costs: dict[str, dict[str, float]] = field(default_factory=dict)
    attitude: str = "minimax"
    cvar_alpha: float = 0.9
    _matrix: CostMatrix = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        try:
            matrix = CostMatrix(self.outcomes, self.costs)
        except ContractError as e:
            raise ContractError(f"invalid loss matrix: {e.message}",
                                code=e.details.get("code", "bad_costs")) from e
        if self.attitude not in RISK_ATTITUDES:
            raise ContractError(
                f"unknown risk attitude {self.attitude!r}; attitudes: "
                f"{list(RISK_ATTITUDES)}", code="bad_risk_attitude")
        if not 0.0 <= self.cvar_alpha < 1.0:
            raise ContractError(
                f"cvar_alpha must be in [0, 1), got {self.cvar_alpha}",
                code="bad_cvar_alpha")
        self._matrix = matrix
        self.outcomes = list(matrix.outcomes)
        self.costs = matrix.to_dict()["costs"]

    @property
    def matrix(self) -> CostMatrix:
        """The validated loss matrix."""
        return self._matrix

    def validate_value(self, value: Any) -> None:
        if value not in self._matrix.outcomes:
            raise ContractError(
                f"{value!r} not in outcomes {list(self._matrix.outcomes)}",
                code="value_outside_outcomes")

    def decide(self, distribution: Mapping[str, float] | None = None
               ) -> tuple[str, float]:
        """Decide per the contract's risk attitude.

        ``minimax`` and ``minimax_regret`` ignore the distribution;
        ``cvar`` requires it.
        """
        if self.attitude == "minimax":
            return minimax_decision(self._matrix)
        if self.attitude == "minimax_regret":
            return minimax_regret_decision(self._matrix)
        if distribution is None:
            raise ContractError("cvar attitude needs a distribution",
                                code="cvar_needs_distribution")
        return cvar_decision(self._matrix, distribution, self.cvar_alpha)

    def expected_cost(self, distribution: Mapping[str, float],
                      decision: str) -> float:
        """Expected loss — the risk-neutral baseline for comparison."""
        return expected_cost(self._matrix, distribution, decision)

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "outcomes": list(self._matrix.outcomes),
            "costs": {p: dict(r)
                      for p, r in self._matrix.to_dict()["costs"].items()},
            "attitude": self.attitude,
        }
        if self.attitude == "cvar":
            d["cvar_alpha"] = self.cvar_alpha
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> RiskContract:
        costs = d.get("costs")
        outcomes = d.get("outcomes")
        if not isinstance(costs, dict) or not isinstance(outcomes, list):
            raise ContractError("risk payload needs 'outcomes' and 'costs'",
                                code="missing_loss_matrix")
        return cls(outcomes=outcomes, costs=costs,
                   attitude=d.get("attitude", "minimax"),
                   cvar_alpha=d.get("cvar_alpha", 0.9), **common)

    def describe(self) -> str:
        extra = (f", alpha={self.cvar_alpha:g}"
                 if self.attitude == "cvar" else "")
        return (f"risk contract {self.name or self.contract_id!r}: "
                f"{len(self._matrix.outcomes)} outcomes, "
                f"attitude={self.attitude}{extra}")
