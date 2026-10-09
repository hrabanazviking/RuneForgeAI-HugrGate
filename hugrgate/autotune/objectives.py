"""Objective specification. Slice 452.

An objective turns a parameter vector into a number the optimizer can
climb. This module defines:

- :class:`Direction` — maximize or minimize;
- :class:`ObjectiveSpec` — one metric: an evaluator, a direction,
  normalization bounds (so composites stay scale-free), and an
  optional target;
- :class:`WeightedObjective` — a scale-free weighted sum of specs;
- :class:`LexicographicObjective` — ordered priorities: never
  sacrifice a higher objective for a lower one;
- :class:`GuardedObjective` — a primary objective fenced by guard
  objectives that must stay above their floors.

All composites expose :meth:`as_callable` returning the plain
``values -> float`` callable the controller's
:meth:`OptimizationController.register_objective` expects. Bad
specifications (unknown metric kind, empty weights, negative
weights, zero-width bounds) raise :class:`ObjectiveError` — a caller
bug, not retryable.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import ObjectiveError

__all__ = [
    "Direction",
    "GuardedObjective",
    "LexicographicObjective",
    "ObjectiveSpec",
    "WeightedObjective",
]


class Direction(str, enum.Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class ObjectiveSpec:
    """One measurable objective over a parameter vector.

    ``evaluate`` maps a full parameter dict to a raw metric value.
    ``bounds`` are the (lo, hi) range used to normalize the metric to
    [0, 1] before composition — required so a weighted sum cannot be
    dominated by whichever metric has the largest raw scale. ``target``
    is an optional aspiration level used by guardrails and reports.
    """

    objective_id: str
    evaluate: Callable[[Mapping[str, Any]], float]
    direction: Direction = Direction.MAXIMIZE
    bounds: tuple[float, float] = (0.0, 1.0)
    target: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.objective_id or not isinstance(self.objective_id, str):
            raise ObjectiveError("objective id must be a non-empty string")
        if not callable(self.evaluate):
            raise ObjectiveError("evaluate must be callable",
                                 objective=self.objective_id)
        lo, hi = self.bounds
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo >= hi:
            raise ObjectiveError("bounds must be finite with lo < hi",
                                 objective=self.objective_id,
                                 bounds=self.bounds)

    def raw(self, values: Mapping[str, Any]) -> float:
        try:
            value = float(self.evaluate(values))
        except ObjectiveError:
            raise
        except Exception as exc:  # evaluator isolation
            raise ObjectiveError("objective evaluator raised",
                                 objective=self.objective_id,
                                 error=repr(exc)) from exc
        if not math.isfinite(value):
            raise ObjectiveError("objective evaluator returned non-finite",
                                 objective=self.objective_id, value=value)
        return value

    def normalized(self, values: Mapping[str, Any]) -> float:
        """Raw value mapped to [0, 1] with 1.0 = best achievable."""
        lo, hi = self.bounds
        v = self.raw(values)
        ratio = min(1.0, max(0.0, (v - lo) / (hi - lo)))
        return ratio if self.direction is Direction.MAXIMIZE else 1.0 - ratio

    def meets_target(self, values: Mapping[str, Any]) -> bool:
        if self.target is None:
            return True
        v = self.raw(values)
        return v >= self.target if self.direction is Direction.MAXIMIZE \
            else v <= self.target

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_id": self.objective_id,
            "direction": self.direction.value,
            "bounds": list(self.bounds),
            "target": self.target,
            "description": self.description,
        }


@dataclass(frozen=True)
class WeightedObjective:
    """Scale-free weighted sum of normalized objectives."""

    objective_id: str
    parts: tuple[tuple[ObjectiveSpec, float], ...]

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ObjectiveError("objective id must be non-empty")
        if not self.parts:
            raise ObjectiveError("weighted objective needs at least one part",
                                 objective=self.objective_id)
        ids = [p.objective_id for p, _ in self.parts]
        if len(set(ids)) != len(ids):
            raise ObjectiveError("duplicate objective ids in weighted sum",
                                 objective=self.objective_id)
        for _, w in self.parts:
            if not math.isfinite(w) or w < 0:
                raise ObjectiveError("weights must be finite and >= 0",
                                     objective=self.objective_id)
        total = sum(w for _, w in self.parts)
        if total <= 0:
            raise ObjectiveError("weights must sum to a positive value",
                                 objective=self.objective_id)

    def normalized(self, values: Mapping[str, Any]) -> float:
        total = sum(w for _, w in self.parts)
        return sum(spec.normalized(values) * w
                   for spec, w in self.parts) / total

    def as_callable(self) -> Callable[[Mapping[str, Any]], float]:
        return self.normalized


@dataclass(frozen=True)
class LexicographicObjective:
    """Ordered priorities — a strict total order over specs.

    Comparison is lexicographic on the normalized values: the first
    spec decides unless the two candidates tie within ``tolerance``.
    ``as_callable`` cannot express a total order as a scalar, so the
    comparison is exposed via :meth:`better` and a scalar *rank*
    surrogate (base-2 positional encoding) for controllers that need
    a single number.
    """

    objective_id: str
    specs: tuple[ObjectiveSpec, ...]
    tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ObjectiveError("objective id must be non-empty")
        if not self.specs:
            raise ObjectiveError("lexicographic objective needs specs",
                                 objective=self.objective_id)
        if self.tolerance < 0:
            raise ObjectiveError("tolerance must be >= 0",
                                 objective=self.objective_id)

    def vector(self, values: Mapping[str, Any]) -> tuple[float, ...]:
        return tuple(s.normalized(values) for s in self.specs)

    def better(self, a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
        va, vb = self.vector(a), self.vector(b)
        for x, y in zip(va, vb, strict=True):
            if abs(x - y) > self.tolerance:
                return x > y
        return False  # tie: not better

    def rank(self, values: Mapping[str, Any]) -> float:
        """Scalar surrogate: base-2 positional encoding of the vector."""
        score = 0.0
        for i, v in enumerate(self.vector(values)):
            score += v * (2.0 ** (len(self.specs) - 1 - i))
        return score

    def as_callable(self) -> Callable[[Mapping[str, Any]], float]:
        return self.rank


@dataclass(frozen=True)
class GuardedObjective:
    """A primary objective fenced by guard floors.

    ``score`` returns the primary's normalized value when every guard
    meets its floor, and ``-inf`` otherwise — infeasible candidates
    can never beat feasible ones, no matter how good the primary is.
    """

    objective_id: str
    primary: ObjectiveSpec
    guards: tuple[tuple[ObjectiveSpec, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ObjectiveError("objective id must be non-empty")
        for _spec, floor in self.guards:
            if not math.isfinite(floor):
                raise ObjectiveError("guard floor must be finite",
                                     objective=self.objective_id)

    def feasible(self, values: Mapping[str, Any]) -> bool:
        return all(spec.normalized(values) >= floor
                   for spec, floor in self.guards)

    def normalized(self, values: Mapping[str, Any]) -> float:
        if not self.feasible(values):
            return float("-inf")
        return self.primary.normalized(values)

    def violations(self, values: Mapping[str, Any]) -> list[str]:
        return [spec.objective_id for spec, floor in self.guards
                if spec.normalized(values) < floor]

    def as_callable(self) -> Callable[[Mapping[str, Any]], float]:
        return self.normalized


def metric_from_samples(key: str,
                        direction: Direction = Direction.MAXIMIZE,
                        bounds: tuple[float, float] = (0.0, 1.0)
                        ) -> ObjectiveSpec:
    """Build an objective that reads a named metric from the values map.

    Tuners stash measured metrics into the candidate values dict under
    ``"metrics"``; this helper turns ``metrics[key]`` into an objective
    without a custom evaluator.
    """
    def _eval(values: Mapping[str, Any]) -> float:
        metrics = values.get("metrics", {})
        if not isinstance(metrics, Mapping) or key not in metrics:
            raise ObjectiveError(f"metric {key!r} missing from values")
        return float(metrics[key])

    return ObjectiveSpec(objective_id=f"metric:{key}", evaluate=_eval,
                         direction=direction, bounds=bounds,
                         description=f"sampled metric {key}")
