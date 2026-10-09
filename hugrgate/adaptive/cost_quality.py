"""Cost-quality objective. Slice 132.

Also home to Campaign VI's shared routing contracts: :class:`RoutingCandidate`
(the per-arm estimate every objective scores) and :class:`RouteObjective`
(the scoring interface slices 133-136 implement).

A router that maximizes quality alone will happily spend a fortune; one
that minimizes cost alone will route everything to the cheapest broken
backend. :class:`CostQualityObjective` scalarizes the trade-off:

    score = quality_weight * quality - cost_weight * (cost / cost_scale)

``cost_scale`` keeps the two terms commensurable (dollars and quality
live on different planets); the weights let the application declare how
much quality a unit of money is worth. Both weights must be
non-negative, and at least one must be positive - an objective that
scores everything zero routes at random, which is a bug, not a policy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "CostQualityObjective",
    "RouteObjective",
    "RoutingCandidate",
]


@dataclass(frozen=True)
class RoutingCandidate:
    """One arm's estimated cost/quality/latency/energy profile.

    This is the shared estimate contract for all Campaign VI objectives.
    ``privacy_ok`` is advisory only - the privacy-constrained objective
    (slice 135) re-derives permission from ``is_remote`` /
    ``data_retained`` and the policy rather than trusting the flag.
    """

    name: str
    quality: float       # expected quality in [0, 1]
    cost: float          # monetary units, >= 0
    latency_ms: float    # >= 0
    energy_wh: float     # >= 0
    privacy_ok: bool = True
    is_remote: bool = False
    data_retained: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise SpecError("candidate name must be a non-empty string")
        if not 0.0 <= self.quality <= 1.0:
            raise SpecError(f"quality out of [0,1]: {self.quality!r}")
        for attr in ("cost", "latency_ms", "energy_wh"):
            if getattr(self, attr) < 0:
                raise SpecError(
                    f"{attr} must be >= 0, got {getattr(self, attr)!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quality": self.quality,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "energy_wh": self.energy_wh,
            "privacy_ok": self.privacy_ok,
            "is_remote": self.is_remote,
            "data_retained": self.data_retained,
        }


class RouteObjective(ABC):
    """Scores one :class:`RoutingCandidate`; higher is better."""

    name: str = "objective"

    @abstractmethod
    def score(self, candidate: RoutingCandidate) -> float:
        """Scalar score for this candidate (higher = better)."""

    def rank(self, candidates: list[RoutingCandidate]) -> list[RoutingCandidate]:
        """Candidates sorted best-first (stable; ties keep input order)."""
        scored = [(self.score(c), i, c)
                  for i, c in enumerate(candidates)]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [c for _, _, c in scored]


class CostQualityObjective(RouteObjective):
    """Trade expected quality against monetary cost."""

    name = "cost_quality"

    def __init__(self, *, quality_weight: float = 1.0,
                 cost_weight: float = 1.0,
                 cost_scale: float = 1.0) -> None:
        if quality_weight < 0 or cost_weight < 0:
            raise SpecError(
                "objective weights must be non-negative, got "
                f"quality_weight={quality_weight}, cost_weight={cost_weight}")
        if quality_weight == 0 and cost_weight == 0:
            raise SpecError(
                "at least one of quality_weight/cost_weight must be positive")
        if cost_scale <= 0:
            raise SpecError(f"cost_scale must be > 0, got {cost_scale}")
        self.quality_weight = quality_weight
        self.cost_weight = cost_weight
        self.cost_scale = cost_scale

    def score(self, candidate: RoutingCandidate) -> float:
        return (self.quality_weight * candidate.quality
                - self.cost_weight * (candidate.cost / self.cost_scale))

    def max_affordable_quality_loss(self, extra_cost: float) -> float:
        """How much quality may drop to justify ``extra_cost``?

        Inverts the scalarization: a pricier arm is worth it iff its
        quality gain exceeds ``cost_weight/quality_weight`` per scaled
        cost unit. Returns 0.0 when quality is unweighted.
        """
        if extra_cost < 0:
            raise SpecError(f"extra_cost must be >= 0, got {extra_cost}")
        if self.quality_weight == 0:
            return 0.0
        return (self.cost_weight / self.quality_weight) * \
            (extra_cost / self.cost_scale)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "quality_weight": self.quality_weight,
            "cost_weight": self.cost_weight,
            "cost_scale": self.cost_scale,
        }
