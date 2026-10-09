"""Distribution constraints — what a healthy distribution looks like.

Gjallarbrú slice 035.

``validate_result`` (and slice 033's ordinal check) verify that a
distribution is *well-formed*: keys in the outcome space, values in
[0,1], sum ≈ 1. They say nothing about whether it is *sane*: a backend
that always emits ``{"a": 1.0}`` is well-formed and useless. This module
adds declarative, serializable constraints over distributions:

- ``min_top1`` / ``max_top1`` — decisiveness floor / overconfidence cap;
- ``min_margin`` — gap between the top two probabilities;
- ``min_entropy`` / ``max_entropy`` — Shannon entropy bounds (nats);
- ``max_support`` — at most *k* outcomes with mass above ε;
- ``min_mass`` — a label set must carry at least *p* combined mass.

:class:`DistributionContract` (kind ``"distribution"``) binds an outcome
space to a constraint list: values validate against the outcomes,
distributions validate against the constraints.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "DISTRIBUTION_CONSTRAINT_OPS",
    "SUPPORT_EPSILON",
    "DistributionConstraint",
    "DistributionContract",
    "shannon_entropy",
]

#: Supported distribution-constraint operators.
DISTRIBUTION_CONSTRAINT_OPS = (
    "min_top1", "max_top1", "min_margin",
    "min_entropy", "max_entropy", "max_support", "min_mass",
)

#: Probabilities at or below this count as zero for support counting.
SUPPORT_EPSILON = 1e-9


def shannon_entropy(distribution: Mapping[str, float]) -> float:
    """Shannon entropy in nats (zero-mass entries contribute 0)."""
    h = 0.0
    for p in distribution.values():
        if p > 0.0:
            h -= p * math.log(p)
    return h


def _sorted_probs(distribution: Mapping[str, float]) -> list[float]:
    return sorted(distribution.values(), reverse=True)


@dataclass(frozen=True)
class DistributionConstraint:
    """One declarative invariant over a probability distribution."""

    op: str
    threshold: float = 0.0
    labels: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if self.op not in DISTRIBUTION_CONSTRAINT_OPS:
            raise ContractError(
                f"unknown distribution constraint op {self.op!r}; ops: "
                f"{list(DISTRIBUTION_CONSTRAINT_OPS)}",
                code="bad_distribution_op")
        if self.op == "max_support":
            if (isinstance(self.threshold, bool)
                    or not float(self.threshold).is_integer()
                    or self.threshold < 1):
                raise ContractError("max_support needs an integer ≥ 1",
                                    code="bad_distribution_threshold")
        elif self.op == "min_mass":
            if not self.labels:
                raise ContractError("min_mass needs ≥1 label",
                                    code="bad_distribution_labels")
            if not 0.0 <= self.threshold <= 1.0:
                raise ContractError("min_mass threshold must be in [0,1]",
                                    code="bad_distribution_threshold")
        else:
            if isinstance(self.threshold, bool) or not isinstance(
                    self.threshold, (int, float)):
                raise ContractError(
                    f"op {self.op!r} needs a numeric threshold",
                    code="bad_distribution_threshold")
            if self.op in ("min_top1", "max_top1", "min_margin"):
                if not 0.0 <= self.threshold <= 1.0:
                    raise ContractError(
                        f"op {self.op!r} threshold must be in [0,1]",
                        code="bad_distribution_threshold")
            if self.op in ("min_entropy", "max_entropy"):
                if self.threshold < 0.0:
                    raise ContractError("entropy threshold must be ≥ 0",
                                        code="bad_distribution_threshold")
        if self.labels and self.op != "min_mass":
            raise ContractError(f"op {self.op!r} takes no labels",
                                code="bad_distribution_labels")
        if any(not isinstance(lbl, str) or not lbl for lbl in self.labels):
            raise ContractError("constraint labels must be non-empty strings",
                                code="bad_distribution_labels")
        if not isinstance(self.description, str):
            raise ContractError("description must be a string",
                                code="bad_distribution_description")

    # -- evaluation --------------------------------------------------------

    def _base_problems(self, distribution: Any,
                       ) -> list[str] | None:
        """Well-formedness problems, or None when the mapping is sane."""
        if not isinstance(distribution, Mapping) or not distribution:
            return ["distribution must be a non-empty mapping"]
        problems = []
        for k, v in distribution.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                problems.append(f"p({k!r}) is not numeric: {v!r}")
            elif not 0.0 <= v <= 1.0:
                problems.append(f"p({k!r}) outside [0,1]: {v}")
        total = sum(v for v in distribution.values()
                    if isinstance(v, (int, float)) and not isinstance(v, bool))
        if abs(total - 1.0) > 1e-6:
            problems.append(f"distribution sums to {total}, not 1")
        return problems or None

    def check(self, distribution: Any) -> str | None:
        """Violation message, or None when the constraint holds.

        Never raises on malformed input — malformed distributions are
        reported as violations.
        """
        base = self._base_problems(distribution)
        if base is not None:
            return ("distribution constraint "
                    f"{self.describe()}: malformed distribution: "
                    + "; ".join(base))
        assert isinstance(distribution, Mapping)
        probs = _sorted_probs(distribution)
        top1 = probs[0]
        if self.op == "min_top1":
            ok = top1 >= self.threshold
            detail = f"top1={top1:.4f} < {self.threshold}"
        elif self.op == "max_top1":
            ok = top1 <= self.threshold
            detail = f"top1={top1:.4f} > {self.threshold}"
        elif self.op == "min_margin":
            margin = top1 - (probs[1] if len(probs) > 1 else 0.0)
            ok = margin >= self.threshold
            detail = f"margin={margin:.4f} < {self.threshold}"
        elif self.op == "min_entropy":
            h = shannon_entropy(distribution)
            ok = h >= self.threshold
            detail = f"entropy={h:.4f} < {self.threshold}"
        elif self.op == "max_entropy":
            h = shannon_entropy(distribution)
            ok = h <= self.threshold
            detail = f"entropy={h:.4f} > {self.threshold}"
        elif self.op == "max_support":
            support = sum(1 for p in probs if p > SUPPORT_EPSILON)
            ok = support <= int(self.threshold)
            detail = f"support={support} > {int(self.threshold)}"
        else:  # min_mass
            mass = sum(distribution.get(lbl, 0.0) for lbl in self.labels)
            ok = mass >= self.threshold
            detail = (f"mass({list(self.labels)})={mass:.4f} "
                      f"< {self.threshold}")
        if ok:
            return None
        msg = f"distribution constraint violated: {self.describe()} ({detail})"
        if self.description:
            msg += f" — {self.description}"
        return msg

    def describe(self) -> str:
        """Human-readable constraint, e.g. ``min_top1(0.7)``."""
        if self.op == "min_mass":
            return f"min_mass({list(self.labels)}, {self.threshold})"
        return f"{self.op}({self.threshold:g})"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"op": self.op, "threshold": self.threshold}
        if self.labels:
            d["labels"] = list(self.labels)
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DistributionConstraint:
        if not isinstance(d, Mapping):
            raise ContractError("distribution constraint must be a mapping",
                                code="bad_distribution_constraint")
        try:
            return cls(op=d["op"], threshold=d.get("threshold", 0.0),
                       labels=tuple(d.get("labels", ())),
                       description=d.get("description", ""))
        except KeyError as e:
            raise ContractError(
                f"distribution constraint missing key: {e}",
                code="bad_distribution_constraint") from None


@register_kind
@dataclass
class DistributionContract(DecisionContract):
    """An outcome space with distribution health constraints (kind
    ``"distribution"``)."""

    kind: ClassVar[str] = "distribution"

    outcomes: list[str] = field(default_factory=list)
    constraints: list[DistributionConstraint] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.outcomes or not isinstance(self.outcomes, list):
            raise ContractError("distribution contract needs a non-empty "
                                "'outcomes' list", code="no_outcomes")
        if len(set(self.outcomes)) != len(self.outcomes):
            raise ContractError("outcomes must be unique",
                                code="duplicate_outcomes")
        if any(not isinstance(o, str) or not o for o in self.outcomes):
            raise ContractError("outcomes must be non-empty strings",
                                code="bad_outcome")
        self.outcomes = list(self.outcomes)
        if not isinstance(self.constraints, list):
            raise ContractError("'constraints' must be a list",
                                code="bad_constraints")
        for c in self.constraints:
            if not isinstance(c, DistributionConstraint):
                raise ContractError(
                    "constraints must be DistributionConstraint instances",
                    code="bad_constraint")
            if c.op == "min_mass":
                unknown = [lbl for lbl in c.labels if lbl not in self.outcomes]
                if unknown:
                    raise ContractError(
                        f"min_mass labels unknown to outcomes: {unknown}",
                        code="constraint_on_unknown_outcome")

    # -- validation ----------------------------------------------------------

    def validate_value(self, value: Any) -> None:
        if value not in self.outcomes:
            raise ContractError(
                f"{value!r} not in outcomes {self.outcomes}",
                code="value_outside_outcomes")

    def distribution_violations(
            self, distribution: Mapping[str, float]) -> list[str]:
        """Well-formedness + constraint violations (possibly empty)."""
        problems: list[str] = []
        if not isinstance(distribution, Mapping):
            return ["distribution must be a mapping"]
        bad_keys = [k for k in distribution if k not in self.outcomes]
        if bad_keys:
            problems.append(
                f"distribution keys outside outcomes: {bad_keys}")
        for c in self.constraints:
            msg = c.check(distribution)
            if msg is not None:
                problems.append(msg)
        return problems

    def validate_distribution(self, distribution: Any) -> None:
        """Raise ContractError aggregating every distribution problem."""
        problems = self.distribution_violations(distribution)
        if problems:
            raise ContractError(
                f"{len(problems)} distribution violation(s):\n" +
                "\n".join(f"  - {p}" for p in problems),
                code="distribution_violation", violations=problems)

    def check_distribution(self, distribution: Any) -> list[str]:
        """Non-raising distribution validation."""
        try:
            self.validate_distribution(distribution)
            return []
        except ContractError as e:
            return [e.message]

    # -- serialization ---------------------------------------------------------

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"outcomes": list(self.outcomes)}
        if self.constraints:
            d["constraints"] = [c.to_dict() for c in self.constraints]
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> DistributionContract:
        outcomes = d.get("outcomes")
        if not isinstance(outcomes, list):
            raise ContractError("distribution payload needs an 'outcomes' "
                                "list", code="missing_outcomes")
        raw = d.get("constraints", [])
        if not isinstance(raw, list):
            raise ContractError("'constraints' must be a list",
                                code="bad_constraints")
        return cls(outcomes=outcomes,
                   constraints=[DistributionConstraint.from_dict(v)
                                for v in raw],
                   **common)

    def describe(self) -> str:
        return (f"distribution contract {self.name or self.contract_id!r}: "
                f"{len(self.outcomes)} outcomes, "
                f"{len(self.constraints)} constraint(s)")
