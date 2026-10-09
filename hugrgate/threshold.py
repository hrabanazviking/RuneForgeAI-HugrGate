"""Thresholding — per-option, ordinal-cumulative, and numeric-band gates.

Slice 16. The policy's ``minimum_probability`` is a single global floor;
this module adds finer gates that the application configures per spec:

- **per-option thresholds**: ``{"escalate": 0.9}`` — the winning option
  must carry at least that much of the distribution mass.
- **ordinal cumulative thresholds**: ``("moderate", 0.8)`` — for ordinal
  specs, P(level >= "moderate") must clear the bar ("at least moderate").
- **numeric band thresholds**: the numeric value lands in a named band
  (e.g. ``normal`` / ``watch`` / ``alert``); each band may demand its own
  minimum probability.

:func:`apply_thresholds` runs the policy floor first, then the
configured gates. The first failing gate turns the result into an
abstention (via :mod:`hugrgate.abstain`) whose reason names the gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.abstain import abstain
from hugrgate.errors import PolicyError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "NumericBand",
    "ThresholdConfig",
    "apply_thresholds",
    "classify_numeric_band",
    "ordinal_cumulative_probability",
]


@dataclass
class NumericBand:
    """A named interval of a numeric decision space."""
    name: str
    lo: float
    hi: float
    min_probability: float = 0.0

    def __post_init__(self):
        if self.lo > self.hi:
            raise PolicyError(
                f"NumericBand {self.name!r}: lo ({self.lo}) > hi ({self.hi})")
        if not 0.0 <= self.min_probability <= 1.0:
            raise PolicyError("min_probability must be in [0,1]")

    def contains(self, value: float) -> bool:
        return self.lo <= value <= self.hi

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "lo": self.lo, "hi": self.hi,
                "min_probability": self.min_probability}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> NumericBand:
        return cls(name=d["name"], lo=d["lo"], hi=d["hi"],
                   min_probability=d.get("min_probability", 0.0))


@dataclass
class ThresholdConfig:
    """Finer-than-policy acceptance gates."""
    per_option: dict[str, float] = field(default_factory=dict)
    ordinal_minimum: tuple[str, float] | None = None  # (level, min P(>=level))
    numeric_bands: list[NumericBand] = field(default_factory=list)
    global_minimum: float | None = None  # overrides policy floor if set

    def __post_init__(self):
        for opt, thr in self.per_option.items():
            if not isinstance(opt, str) or not opt:
                raise PolicyError(
                    f"per-option threshold keys must be non-empty strings, "
                    f"got {opt!r}")
            if not 0.0 <= thr <= 1.0:
                raise PolicyError(
                    f"per-option threshold for {opt!r} must be in [0,1]")
        if self.ordinal_minimum is not None:
            level, thr = self.ordinal_minimum
            if not isinstance(level, str) or not level:
                raise PolicyError(
                    f"ordinal_minimum level must be a non-empty string, "
                    f"got {level!r}")
            if not 0.0 <= thr <= 1.0:
                raise PolicyError("ordinal threshold must be in [0,1]")
        if self.global_minimum is not None and not 0.0 <= self.global_minimum <= 1.0:
            raise PolicyError("global_minimum must be in [0,1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "per_option": dict(self.per_option),
            "ordinal_minimum": (list(self.ordinal_minimum)
                                if self.ordinal_minimum is not None else None),
            "numeric_bands": [b.to_dict() for b in self.numeric_bands],
            "global_minimum": self.global_minimum,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ThresholdConfig:
        unknown = set(d) - {"per_option", "ordinal_minimum",
                             "numeric_bands", "global_minimum"}
        if unknown:
            raise PolicyError(
                f"unknown ThresholdConfig key(s): {sorted(unknown)}")
        ordinal = d.get("ordinal_minimum")
        return cls(
            per_option=dict(d.get("per_option") or {}),
            ordinal_minimum=tuple(ordinal) if ordinal is not None else None,
            numeric_bands=[NumericBand.from_dict(b)
                           for b in d.get("numeric_bands") or []],
            global_minimum=d.get("global_minimum"),
        )


def ordinal_cumulative_probability(result: DecisionResult,
                                   spec: DecisionSpec,
                                   level: str) -> float:
    """P(decision >= level) for an ordinal spec.

    Sums the distribution over ``level`` and every level above it.
    Falls back to the result probability when the distribution is empty.
    """
    if spec.type != "ordinal" or not spec.levels:
        raise PolicyError(
            "ordinal_cumulative_probability needs an ordinal spec")
    if level not in spec.levels:
        raise PolicyError(
            f"level {level!r} not in spec levels {spec.levels}")
    idx = spec.levels.index(level)
    if not result.distribution:
        return result.probability
    return sum(result.distribution.get(lv, 0.0) for lv in spec.levels[idx:])


def classify_numeric_band(value: float,
                           bands: list[NumericBand]) -> NumericBand | None:
    """First band containing ``value``; None when the value is unbanned."""
    for band in bands:
        if band.contains(value):
            return band
    return None


def apply_thresholds(result: DecisionResult, spec: DecisionSpec,
                     config: ThresholdConfig | None = None,
                     policy: DecisionPolicy | None = None
                     ) -> DecisionResult:
    """Apply the policy floor and the configured gates to a result.

    Returns the (accepted) result when every gate passes, otherwise an
    abstention result naming the failed gate. Never raises.
    """
    config = config or ThresholdConfig()

    # 1. Global floor: config override wins, else the policy's floor.
    floor = config.global_minimum
    if floor is None and policy is not None:
        floor = policy.minimum_probability
    if floor is not None and result.probability < floor:
        return abstain(spec, reason=f"probability {result.probability:.3f} "
                                    f"below threshold floor {floor:.3f}",
                       backend=result.backend)

    # 2. Per-option gate on the winning option's distribution mass.
    if result.value is not None and result.value in config.per_option:
        need = config.per_option[result.value]
        mass = result.distribution.get(result.value, result.probability)
        if mass < need:
            return abstain(
                spec,
                reason=f"P({result.value!r})={mass:.3f} below per-option "
                       f"threshold {need:.3f}",
                backend=result.backend)

    # 3. Ordinal cumulative gate ("at least <level>").
    if config.ordinal_minimum is not None and spec.type == "ordinal":
        level, need = config.ordinal_minimum
        cumulative = ordinal_cumulative_probability(result, spec, level)
        if cumulative < need:
            return abstain(
                spec,
                reason=f"P(at least {level!r})={cumulative:.3f} below "
                       f"threshold {need:.3f}",
                backend=result.backend)

    # 4. Numeric band gate.
    if config.numeric_bands and spec.type == "numeric":
        value = result.value
        band = classify_numeric_band(value, config.numeric_bands) \
            if isinstance(value, (int, float)) else None
        if band is None:
            return abstain(
                spec,
                reason=f"numeric value {value!r} falls in no defined band",
                backend=result.backend)
        result.metadata["numeric_band"] = band.name
        if result.probability < band.min_probability:
            return abstain(
                spec,
                reason=f"probability {result.probability:.3f} below band "
                       f"{band.name!r} threshold {band.min_probability:.3f}",
                backend=result.backend)

    result.accepted = True
    result.metadata.setdefault("thresholds_passed", True)
    return result
