"""Constraint specification. Slice 453.

Constraints are the fences inside which the optimizer may roam. Where
the :class:`ConfigStore` enforces *hard* validity (type, registered
name, absolute bounds), constraints express *policy*: operating
envelopes tighter than the hard bounds, conditional rules ("if the
canary backend is on, the shadow backend must be off"), and budget
caps ("the three latency budgets must sum under 900 ms").

A constraint is a predicate over the full candidate parameter dict.
A broken constraint raises :class:`ConstraintViolation` — the
controller treats that as a routine proposal rejection, not a crash.

Provided:

- :class:`ConstraintSpec` — id, predicate, human message, severity;
- :class:`Violation` — structured record of one breach;
- :class:`ConstraintSet` — ordered set with ``validate`` (raise on
  first breach), ``validate_all`` (collect every breach), and
  ``as_callables`` for :meth:`OptimizationController.register_constraint`;
- builders: :func:`within_bounds`, :func:`requires`, :func:`implies`,
  :func:`mutual_exclusion`, :func:`sum_leq`, :func:`change_within`.

Privacy note: constraint messages must not echo secret parameter
values — builders only name the parameter and the rule, never the
value, in the violation message.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import ConstraintViolation

__all__ = [
    "ConstraintSet",
    "ConstraintSpec",
    "Violation",
    "change_within",
    "implies",
    "mutual_exclusion",
    "requires",
    "sum_leq",
    "within_bounds",
]


@dataclass(frozen=True)
class Violation:
    """One breached constraint."""

    constraint_id: str
    message: str
    severity: str = "hard"

    def to_dict(self) -> dict[str, Any]:
        return {"constraint_id": self.constraint_id,
                "message": self.message, "severity": self.severity}


@dataclass(frozen=True)
class ConstraintSpec:
    """A named predicate over a candidate parameter dict."""

    constraint_id: str
    predicate: Callable[[Mapping[str, Any]], bool]
    message: str
    severity: str = "hard"  # "hard" rejects; "soft" warns (slice 472 uses)

    def check(self, values: Mapping[str, Any]) -> Violation | None:
        try:
            ok = bool(self.predicate(values))
        except Exception as exc:  # predicate isolation
            raise ConstraintViolation(
                f"constraint {self.constraint_id} predicate raised",
                constraint=self.constraint_id,
                error=repr(exc)) from exc
        if not ok:
            return Violation(constraint_id=self.constraint_id,
                             message=self.message, severity=self.severity)
        return None

    def as_callable(self) -> Callable[[Mapping[str, Any]], None]:
        def _check(values: Mapping[str, Any]) -> None:
            violation = self.check(values)
            if violation is not None:
                raise ConstraintViolation(
                    violation.message, constraint=violation.constraint_id)
        return _check


class ConstraintSet:
    """An ordered, deduplicated set of constraints."""

    def __init__(self, constraints: Sequence[ConstraintSpec] = ()) -> None:
        self._constraints: list[ConstraintSpec] = []
        for c in constraints:
            self.add(c)

    def add(self, constraint: ConstraintSpec) -> None:
        if any(c.constraint_id == constraint.constraint_id
               for c in self._constraints):
            raise ConstraintViolation("duplicate constraint id",
                                      constraint=constraint.constraint_id)
        self._constraints.append(constraint)

    def __len__(self) -> int:
        return len(self._constraints)

    @property
    def ids(self) -> list[str]:
        return [c.constraint_id for c in self._constraints]

    def validate(self, values: Mapping[str, Any]) -> None:
        """Raise :class:`ConstraintViolation` on the first breach."""
        for c in self._constraints:
            violation = c.check(values)
            if violation is not None:
                raise ConstraintViolation(
                    violation.message, constraint=violation.constraint_id)

    def validate_all(self, values: Mapping[str, Any]) -> list[Violation]:
        """Collect every breach without raising."""
        out: list[Violation] = []
        for c in self._constraints:
            violation = c.check(values)
            if violation is not None:
                out.append(violation)
        return out

    def as_callables(self) -> list[Callable[[Mapping[str, Any]], None]]:
        return [c.as_callable() for c in self._constraints]


# -- builders -----------------------------------------------------------

def within_bounds(param: str, lo: float, hi: float,
                  constraint_id: str | None = None) -> ConstraintSpec:
    """Soft operating envelope for a numeric parameter."""
    cid = constraint_id or f"within_bounds:{param}"
    return ConstraintSpec(
        constraint_id=cid,
        predicate=lambda v: v.get(param) is not None
        and lo <= float(v[param]) <= hi,
        message=f"{param} must stay within [{lo}, {hi}]")


def requires(param: str, predicate: Callable[[Any], bool],
             message: str,
             constraint_id: str | None = None) -> ConstraintSpec:
    """A parameter must satisfy an arbitrary predicate."""
    cid = constraint_id or f"requires:{param}"
    return ConstraintSpec(
        constraint_id=cid,
        predicate=lambda v: param in v and predicate(v[param]),
        message=message)


def implies(param_a: str, value_a: Any, param_b: str,
            allowed: Sequence[Any],
            constraint_id: str | None = None) -> ConstraintSpec:
    """If ``param_a == value_a`` then ``param_b`` must be in ``allowed``."""
    cid = constraint_id or f"implies:{param_a}={value_a}->{param_b}"
    allowed_set = tuple(allowed)
    return ConstraintSpec(
        constraint_id=cid,
        predicate=lambda v: v.get(param_a) != value_a
        or v.get(param_b) in allowed_set,
        message=f"when {param_a}={value_a!r}, {param_b} must be one of "
                f"{list(allowed_set)}")


def mutual_exclusion(params: Sequence[str],
                     constraint_id: str | None = None) -> ConstraintSpec:
    """At most one truthy parameter among the set may be active."""
    names = tuple(params)
    cid = constraint_id or f"mutual_exclusion:{','.join(names)}"
    return ConstraintSpec(
        constraint_id=cid,
        predicate=lambda v: sum(1 for p in names if v.get(p)) <= 1,
        message=f"at most one of {list(names)} may be active")


def sum_leq(params: Sequence[str], cap: float,
            constraint_id: str | None = None) -> ConstraintSpec:
    """The named numeric parameters must sum to at most ``cap``."""
    names = tuple(params)
    cid = constraint_id or f"sum_leq:{','.join(names)}"
    return ConstraintSpec(
        constraint_id=cid,
        predicate=lambda v: sum(float(v[p]) for p in names
                                if p in v and v[p] is not None) <= cap,
        message=f"sum of {list(names)} must be <= {cap}")


def change_within(param: str, baseline: Mapping[str, Any],
                  max_delta: float,
                  constraint_id: str | None = None) -> ConstraintSpec:
    """A parameter may not move more than ``max_delta`` from baseline."""
    cid = constraint_id or f"change_within:{param}"
    base = float(baseline[param])
    return ConstraintSpec(
        constraint_id=cid,
        predicate=lambda v: param not in v or v[param] is None
        or abs(float(v[param]) - base) <= max_delta,
        message=f"{param} may not move more than {max_delta} from baseline")
