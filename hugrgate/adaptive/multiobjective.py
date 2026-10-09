"""Multi-objective routing. Slice 136.

Slices 132-135 each optimize one trade-off; real routing cares about
all of them at once. :class:`MultiObjectiveRouter` composes objectives
two ways:

- **Weighted sum** - ``score = Σ wᵢ · objectiveᵢ(candidate)``. Simple,
  differentiable-ish, and honest about its value judgments: the weights
  *are* the policy.
- **Lexicographic** - objectives ordered by priority; the first
  objective that distinguishes the candidates decides. For "never trade
  X for Y" requirements that weights can't express.

Plus :func:`pareto_frontier`, which finds the non-dominated set over
(quality, -cost, -latency, -energy): the candidates no other candidate
beats on every axis. The frontier is the honest answer to "what are my
real options?" before any scalarization picks a winner.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hugrgate.adaptive.cost_quality import (
    RouteObjective,
    RoutingCandidate,
)
from hugrgate.errors import SpecError

__all__ = [
    "MODES",
    "MultiObjectiveRouter",
    "dominates",
    "pareto_frontier",
]

MODES = ("weighted_sum", "lexicographic")


def dominates(a: RoutingCandidate, b: RoutingCandidate) -> bool:
    """True iff ``a`` is at least as good as ``b`` on every axis and
    strictly better on at least one: quality ↑, cost ↓, latency ↓,
    energy ↓."""
    better_or_equal = (
        a.quality >= b.quality
        and a.cost <= b.cost
        and a.latency_ms <= b.latency_ms
        and a.energy_wh <= b.energy_wh
    )
    strictly_better = (
        a.quality > b.quality
        or a.cost < b.cost
        or a.latency_ms < b.latency_ms
        or a.energy_wh < b.energy_wh
    )
    return better_or_equal and strictly_better


def pareto_frontier(candidates: Sequence[RoutingCandidate]
                    ) -> list[RoutingCandidate]:
    """The non-dominated subset of ``candidates`` (input order kept)."""
    cands = list(candidates)
    frontier = []
    for i, cand in enumerate(cands):
        if any(dominates(other, cand)
               for j, other in enumerate(cands) if j != i):
            continue
        frontier.append(cand)
    return frontier


class MultiObjectiveRouter:
    """Compose several :class:`RouteObjective` into one routing decision."""

    def __init__(self,
                 objectives: Sequence[tuple[RouteObjective, float]],
                 mode: str = "weighted_sum") -> None:
        if mode not in MODES:
            raise SpecError(
                f"unknown multi-objective mode {mode!r}; expected one of "
                f"{list(MODES)}")
        pairs = list(objectives)
        if not pairs:
            raise SpecError("MultiObjectiveRouter needs at least one objective")
        for obj, weight in pairs:
            if not isinstance(obj, RouteObjective):
                raise SpecError(
                    f"expected RouteObjective, got {type(obj).__name__}")
            if weight < 0:
                raise SpecError(
                    f"objective weight must be >= 0, got {weight}")
        if mode == "weighted_sum" and all(w == 0 for _, w in pairs):
            raise SpecError(
                "weighted_sum needs at least one positive weight")
        self.objectives = pairs
        self.mode = mode

    def score(self, candidate: RoutingCandidate) -> float:
        """Combined scalar score (higher = better).

        Only defined for ``weighted_sum`` mode: lexicographic order is
        not a scalar, so callers must use :meth:`rank` there.
        """
        if self.mode != "weighted_sum":
            raise SpecError(
                "lexicographic mode has no scalar score; use rank()")
        return sum(w * obj.score(candidate) for obj, w in self.objectives)

    def _lexicographic_key(self, candidate: RoutingCandidate) -> tuple:
        return tuple(-obj.score(candidate) for obj, _ in self.objectives)

    def rank(self, candidates: Sequence[RoutingCandidate]
             ) -> list[RoutingCandidate]:
        cands = list(candidates)
        if not cands:
            raise SpecError("cannot rank an empty candidate list")
        if self.mode == "weighted_sum":
            scored = [(self.score(c), i, c) for i, c in enumerate(cands)]
            scored.sort(key=lambda t: (-t[0], t[1]))
            return [c for _, _, c in scored]
        keyed = [(self._lexicographic_key(c), i, c)
                 for i, c in enumerate(cands)]
        keyed.sort(key=lambda t: (t[0], t[1]))
        return [c for _, _, c in keyed]

    def best(self, candidates: Sequence[RoutingCandidate]
             ) -> RoutingCandidate:
        return self.rank(candidates)[0]

    def explain_weights(self) -> list[dict[str, Any]]:
        """The value judgments, made auditable."""
        return [
            {"objective": obj.name, "weight": w,
             "mode": self.mode, "priority": i}
            for i, (obj, w) in enumerate(self.objectives)
        ]
