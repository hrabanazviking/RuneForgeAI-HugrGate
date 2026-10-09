"""Rich ordinal semantics — ordinals you can measure. Gjallarbrú slice 033.

A v1 ordinal spec is pure order: ``low < medium < high``, but nothing says
*how far apart* they are. :class:`OrdinalContract` (kind ``"ordinal"``)
pins every level to a numeric anchor on a scale (default: 0, 1, …, n-1),
which unlocks:

- :meth:`distance` — how far apart two levels are;
- :meth:`interpolate` — map a numeric model output to the nearest level;
- :meth:`expected_anchor` — the expected scale position of a distribution;
- :meth:`validate_distribution` — ordered-distribution sanity (keys ⊆
  levels, values ∈ [0,1], sum ≈ 1).

Anchors must be strictly increasing in level order: the scale never folds
back on itself.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "OrdinalContract",
]


@register_kind
@dataclass
class OrdinalContract(DecisionContract):
    """An ordinal scale with measurable level positions."""

    kind: ClassVar[str] = "ordinal"

    levels: list[str] = field(default_factory=list)
    anchors: dict[str, float] = field(default_factory=dict)
    _positions: list[float] = field(init=False, repr=False, compare=False)
    _rank: dict[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.levels or len(self.levels) < 2:
            raise ContractError("ordinal contract needs ≥2 levels",
                                code="not_enough_levels")
        if len(set(self.levels)) != len(self.levels):
            raise ContractError("ordinal levels must be unique",
                                code="duplicate_levels")
        if any(not isinstance(lbl, str) or not lbl for lbl in self.levels):
            raise ContractError("ordinal levels must be non-empty strings",
                                code="bad_level")
        if not isinstance(self.anchors, dict):
            raise ContractError("'anchors' must be a dict",
                                code="bad_anchors")
        if self.anchors:
            unknown = [k for k in self.anchors if k not in self.levels]
            if unknown:
                raise ContractError(
                    f"anchors for unknown levels: {unknown}",
                    code="anchor_for_unknown_level")
            missing = [lbl for lbl in self.levels if lbl not in self.anchors]
            if missing:
                raise ContractError(
                    f"anchors missing for levels: {missing} "
                    f"(anchor every level or none)",
                    code="partial_anchors")
            for level, pos in self.anchors.items():
                if isinstance(pos, bool) or not isinstance(pos, (int, float)):
                    raise ContractError(
                        f"anchor for {level!r} must be numeric, got {pos!r}",
                        code="bad_anchor")
            positions = [float(self.anchors[lbl]) for lbl in self.levels]
            if any(b <= a for a, b in itertools.pairwise(positions)):
                raise ContractError(
                    f"anchors must be strictly increasing in level order, "
                    f"got {positions}", code="anchors_not_increasing")
            self._positions = positions
        else:
            self._positions = [float(i) for i in range(len(self.levels))]
        self._rank = {lbl: i for i, lbl in enumerate(self.levels)}

    # -- order ---------------------------------------------------------------

    def rank_of(self, level: str) -> int:
        """0-based rank of ``level`` (0 = lowest)."""
        try:
            return self._rank[level]
        except KeyError:
            raise ContractError(
                f"unknown ordinal level {level!r}; levels: {self.levels}",
                code="unknown_level") from None

    def anchor_of(self, level: str) -> float:
        """Numeric scale position of ``level``."""
        return self._positions[self.rank_of(level)]

    def is_ordered(self, a: str, b: str) -> bool:
        """True when ``a`` ranks at or below ``b``."""
        return self.rank_of(a) <= self.rank_of(b)

    def distance(self, a: str, b: str) -> float:
        """Absolute anchor distance between two levels."""
        return abs(self.anchor_of(a) - self.anchor_of(b))

    def levels_between(self, a: str, b: str) -> list[str]:
        """Levels strictly between ``a`` and ``b`` (order-independent)."""
        lo, hi = sorted((self.rank_of(a), self.rank_of(b)))
        return self.levels[lo + 1:hi]

    # -- numeric bridge --------------------------------------------------------

    def interpolate(self, x: float) -> str:
        """Nearest level to numeric ``x``; ties go to the lower rank."""
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ContractError(f"interpolate needs a number, got {x!r}",
                                code="bad_interpolate_arg")
        best, best_d = self.levels[0], abs(x - self._positions[0])
        for level, pos in zip(self.levels[1:], self._positions[1:], strict=True):
            d = abs(x - pos)
            if d < best_d:  # strict: earlier (lower) level wins ties
                best, best_d = level, d
        return best

    def expected_anchor(self, distribution: Mapping[str, float]) -> float:
        """Expected scale position under an ordered distribution."""
        self.validate_distribution(distribution)
        return sum(p * self.anchor_of(level)
                   for level, p in distribution.items())

    # -- validation ------------------------------------------------------------

    def validate_value(self, value: Any) -> None:
        if value not in self._rank:
            raise ContractError(
                f"{value!r} is not an ordinal level; levels: {self.levels}",
                code="unknown_level")

    def validate_distribution(self, distribution: Any) -> None:
        """Keys ⊆ levels, values ∈ [0,1], sum ≈ 1."""
        if not isinstance(distribution, Mapping):
            raise ContractError("distribution must be a mapping",
                                code="bad_distribution")
        bad_keys = [k for k in distribution if k not in self._rank]
        if bad_keys:
            raise ContractError(
                f"distribution keys outside ordinal levels: {bad_keys}",
                code="distribution_key_outside_levels")
        for k, v in distribution.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ContractError(
                    f"distribution[{k!r}] is not a number: {v!r}",
                    code="bad_distribution_value")
            if not 0.0 <= v <= 1.0:
                raise ContractError(
                    f"distribution[{k!r}] out of [0,1]: {v}",
                    code="bad_distribution_value")
        total = sum(distribution.values())
        if abs(total - 1.0) > 1e-6:
            raise ContractError(
                f"distribution must sum to 1, got {total}",
                code="distribution_not_normalized")

    # -- serialization -----------------------------------------------------------

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"levels": list(self.levels)}
        if self.anchors:
            d["anchors"] = {lbl: self.anchors[lbl] for lbl in self.levels}
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> OrdinalContract:
        levels = d.get("levels")
        if not isinstance(levels, list):
            raise ContractError("ordinal payload needs a 'levels' list",
                                code="missing_levels")
        anchors = d.get("anchors", {})
        if not isinstance(anchors, dict):
            raise ContractError("'anchors' must be a dict",
                                code="bad_anchors")
        return cls(levels=levels, anchors=dict(anchors), **common)

    def describe(self) -> str:
        pairs = ", ".join(f"{lbl}@{p:g}" for lbl, p in
                          zip(self.levels, self._positions, strict=True))
        return (f"ordinal contract {self.name or self.contract_id!r}: "
                f"{len(self.levels)} levels ({pairs})")
