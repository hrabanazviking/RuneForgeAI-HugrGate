"""Numeric uncertainty intervals. Gjallarbrú slice 034.

A v1 numeric spec holds a point value in ``[minimum, maximum]``. Real
measurements carry uncertainty: an estimate, an interval around it, and
the confidence that the truth lies inside. This module adds:

- :class:`UncertainValue`: frozen ``(estimate, lower, upper, confidence)``
  with ``lower <= estimate <= upper`` and ``0 < confidence < 1``;
- :class:`NumericIntervalContract` (kind ``"numeric-interval"``): the
  allowed estimate range plus optional ``max_width`` and
  ``min_confidence`` guards; plain numbers validate as zero-width
  intervals (confidence 1.0), so point estimates stay first-class;
- interval algebra: :func:`width`, :func:`contains`, :func:`covers`,
  :func:`intersect` (None when disjoint), :func:`widen`.

All operations are pure and deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from hugrgate.contracts.schema import (
    DecisionContract,
    register_kind,
)
from hugrgate.errors import ContractError

__all__ = [
    "NumericIntervalContract",
    "UncertainValue",
    "coerce",
    "contains",
    "covers",
    "intersect",
    "widen",
    "width",
]


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


@dataclass(frozen=True)
class UncertainValue:
    """A numeric estimate with an uncertainty interval and confidence."""

    estimate: float
    lower: float
    upper: float
    confidence: float = 0.95

    def __post_init__(self) -> None:
        for name in ("estimate", "lower", "upper", "confidence"):
            v = getattr(self, name)
            if not _is_num(v):
                raise ContractError(
                    f"UncertainValue.{name} must be numeric, got {v!r}",
                    code="bad_uncertain_value")
        if not (self.lower <= self.estimate <= self.upper):
            raise ContractError(
                f"need lower <= estimate <= upper, got "
                f"({self.lower}, {self.estimate}, {self.upper})",
                code="inverted_interval")
        if not 0.0 < self.confidence <= 1.0:
            raise ContractError(
                f"confidence must be in (0, 1], got {self.confidence}",
                code="bad_confidence")

    def to_dict(self) -> dict[str, float]:
        return {"estimate": self.estimate, "lower": self.lower,
                "upper": self.upper, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> UncertainValue:
        if not isinstance(d, Mapping):
            raise ContractError("UncertainValue needs a mapping",
                                code="bad_uncertain_value")
        try:
            return cls(estimate=d["estimate"], lower=d["lower"],
                       upper=d["upper"],
                       confidence=d.get("confidence", 0.95))
        except KeyError as e:
            raise ContractError(f"UncertainValue missing key: {e}",
                                code="bad_uncertain_value") from None

    @classmethod
    def point(cls, x: float) -> UncertainValue:
        """A degenerate zero-width interval: a plain point estimate."""
        return cls(estimate=x, lower=x, upper=x, confidence=1.0)


def width(v: UncertainValue) -> float:
    """Interval width (upper - lower)."""
    return v.upper - v.lower


def contains(v: UncertainValue, x: float) -> bool:
    """True when ``x`` lies inside the interval (inclusive)."""
    if not _is_num(x):
        raise ContractError(f"contains needs a number, got {x!r}",
                            code="bad_contains_arg")
    return bool(v.lower <= x <= v.upper)


def covers(a: UncertainValue, b: UncertainValue) -> bool:
    """True when ``a``'s interval fully contains ``b``'s."""
    return bool(a.lower <= b.lower and b.upper <= a.upper)


def intersect(a: UncertainValue, b: UncertainValue) -> UncertainValue | None:
    """Interval intersection, or None when disjoint.

    The estimate is ``a``'s estimate clipped into the overlap; confidence
    is the more conservative (lower) of the two.
    """
    lo, hi = max(a.lower, b.lower), min(a.upper, b.upper)
    if lo > hi:
        return None
    est = min(max(a.estimate, lo), hi)
    return UncertainValue(estimate=est, lower=lo, upper=hi,
                          confidence=min(a.confidence, b.confidence))


def widen(v: UncertainValue, factor: float) -> UncertainValue:
    """Scale the half-widths around the estimate by ``factor`` (≥0)."""
    if not _is_num(factor) or factor < 0:
        raise ContractError(f"widen factor must be ≥ 0, got {factor!r}",
                            code="bad_widen_factor")
    lo = v.estimate - (v.estimate - v.lower) * factor
    hi = v.estimate + (v.upper - v.estimate) * factor
    return UncertainValue(estimate=v.estimate, lower=lo, upper=hi,
                          confidence=v.confidence)


def coerce(value: Any) -> UncertainValue:
    """Plain number → zero-width interval; mapping → UncertainValue."""
    if _is_num(value):
        return UncertainValue.point(float(value))
    if isinstance(value, Mapping):
        return UncertainValue.from_dict(value)
    if isinstance(value, UncertainValue):
        return value
    raise ContractError(
        f"expected a number or uncertainty mapping, got "
        f"{type(value).__name__}", code="bad_uncertain_value")


@register_kind
@dataclass
class NumericIntervalContract(DecisionContract):
    """Numeric decisions with uncertainty (kind ``"numeric-interval"``)."""

    kind: ClassVar[str] = "numeric-interval"

    minimum: float = 0.0
    maximum: float = 1.0
    max_width: float | None = None
    min_confidence: float | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("minimum", "maximum"):
            v = getattr(self, name)
            if not _is_num(v):
                raise ContractError(f"{name} must be numeric, got {v!r}",
                                    code="bad_numeric_bound")
        if not self.minimum < self.maximum:
            raise ContractError("numeric minimum must be < maximum",
                                code="bad_numeric_bound")
        if self.max_width is not None:
            if not _is_num(self.max_width) or self.max_width < 0:
                raise ContractError("max_width must be ≥ 0",
                                    code="bad_max_width")
        if self.min_confidence is not None:
            if (not _is_num(self.min_confidence)
                    or not 0.0 < self.min_confidence <= 1.0):
                raise ContractError("min_confidence must be in (0, 1]",
                                    code="bad_min_confidence")

    def validate_value(self, value: Any) -> None:
        v = coerce(value)
        if not (self.minimum <= v.estimate <= self.maximum):
            raise ContractError(
                f"estimate {v.estimate} outside "
                f"[{self.minimum}, {self.maximum}]",
                code="estimate_out_of_range")
        if not (self.minimum <= v.lower and v.upper <= self.maximum):
            raise ContractError(
                f"interval [{v.lower}, {v.upper}] exceeds "
                f"[{self.minimum}, {self.maximum}]",
                code="interval_out_of_range")
        if self.max_width is not None and width(v) > self.max_width:
            raise ContractError(
                f"interval width {width(v)} exceeds max_width "
                f"{self.max_width}", code="interval_too_wide")
        if (self.min_confidence is not None
                and v.confidence < self.min_confidence):
            raise ContractError(
                f"confidence {v.confidence} below min_confidence "
                f"{self.min_confidence}", code="confidence_too_low")

    def _payload_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"minimum": self.minimum,
                             "maximum": self.maximum}
        if self.max_width is not None:
            d["max_width"] = self.max_width
        if self.min_confidence is not None:
            d["min_confidence"] = self.min_confidence
        return d

    @classmethod
    def _from_payload(cls, d: Mapping[str, Any],
                      common: dict[str, Any]) -> NumericIntervalContract:
        try:
            return cls(minimum=d["minimum"], maximum=d["maximum"],
                       max_width=d.get("max_width"),
                       min_confidence=d.get("min_confidence"), **common)
        except KeyError as e:
            raise ContractError(f"numeric-interval payload missing {e}",
                                code="bad_numeric_payload") from None

    def describe(self) -> str:
        extra = ""
        if self.max_width is not None:
            extra += f", width ≤ {self.max_width:g}"
        if self.min_confidence is not None:
            extra += f", conf ≥ {self.min_confidence:g}"
        return (f"numeric-interval contract {self.name or self.contract_id!r}: "
                f"[{self.minimum:g}, {self.maximum:g}]{extra}")
