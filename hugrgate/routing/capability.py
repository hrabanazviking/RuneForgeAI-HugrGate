"""Capability scoring. Slice 054.

Promotes the slice-053 heuristic into a reasoned, auditable scorer.
:class:`CapabilityScorer` grades a backend for a specific request as a
:class:`CapabilityScore`: a value in [0,1] plus the per-factor breakdown
and human-readable reasons that produced it. Factors:

- **support gate** — ``backend.supports(spec)`` is required; anything
  else scores exactly 0 with the reason recorded.
- **spec-type claim** — explicit listing of the spec type in
  ``capabilities()["spec_types"]``.
- **quality claims** — declared ``accuracy`` / ``reliability`` /
  ``quality`` numbers in [0,1].
- **calibration** — ``calibration_info()["calibrated"]`` earns a bonus;
  a declared expected calibration error (``ece``) discounts the score.
- **feature coverage** — fraction of ``spec.metadata["requires_features"]``
  present in ``capabilities()["features"]``.
- **capacity fit** — declared ``max_options`` / ``max_labels`` limits
  checked against the spec's value-space size; a backend that cannot
  represent the space scores 0.

The final value is a weighted blend, clamped to [0,1] and rounded to 4
decimals so scores are stable and comparable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from hugrgate.backend import Backend
from hugrgate.routing.architecture import RouterContext

__all__ = [
    "CapabilityScore",
    "CapabilityScorer",
]

#: Blend weights for the scored factors.
WEIGHTS = {
    "quality": 0.35,
    "calibration": 0.20,
    "features": 0.20,
    "capacity": 0.15,
    "spec_claim": 0.10,
}


@dataclass
class CapabilityScore:
    """A graded capability verdict for one backend on one request."""

    value: float
    reasons: List[str] = field(default_factory=list)
    factors: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"capability score out of [0,1]: {self.value}")

    def __float__(self) -> float:
        return self.value


class CapabilityScorer:
    """Score backends for a request with an auditable factor breakdown."""

    def __init__(self, weights: Dict[str, float] | None = None):
        self.weights = dict(weights or WEIGHTS)
        if abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ValueError("capability weights must sum to 1.0")

    def score(self, backend: Backend, ctx: RouterContext) -> CapabilityScore:
        reasons: List[str] = []
        if not backend.supports(ctx.spec):
            return CapabilityScore(
                0.0,
                reasons=[f"{backend.name} does not support "
                         f"{ctx.spec.type} specs"],
                factors={"support": 0.0})

        caps = backend.capabilities() or {}
        factors: Dict[str, float] = {}

        # spec-type claim
        claimed = caps.get("spec_types") or []
        factors["spec_claim"] = 1.0 if ctx.spec.type in claimed else 0.4
        reasons.append(
            f"spec_types claim: {ctx.spec.type!r} "
            f"{'listed' if factors['spec_claim'] == 1.0 else 'not listed'}")

        # quality claims
        quality = 0.5
        for key in ("accuracy", "reliability", "quality"):
            value = caps.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and 0.0 <= value <= 1.0:
                quality = max(quality, float(value))
                reasons.append(f"declared {key}={float(value):.2f}")
        factors["quality"] = quality

        # calibration
        cal = backend.calibration_info() or {}
        cal_score = 0.5
        if cal.get("calibrated"):
            cal_score = 0.8
            reasons.append("backend reports calibrated")
        ece = cal.get("ece")
        if isinstance(ece, (int, float)) and 0.0 <= ece <= 1.0:
            cal_score = max(0.0, cal_score - float(ece))
            reasons.append(f"expected calibration error {float(ece):.3f} "
                           f"discounts score")
        factors["calibration"] = round(cal_score, 4)

        # feature coverage
        required = ctx.spec.metadata.get("requires_features") or []
        provided = set(caps.get("features") or [])
        if required:
            hit = sum(1 for f in required if f in provided)
            factors["features"] = round(hit / len(required), 4)
            reasons.append(f"feature coverage {hit}/{len(required)}")
        else:
            factors["features"] = 0.5
            reasons.append("no required features declared")

        # capacity fit
        factors["capacity"] = self._capacity_fit(backend, ctx, caps, reasons)

        value = round(sum(self.weights[k] * factors[k]
                          for k in self.weights), 4)
        value = max(0.0, min(1.0, value))
        return CapabilityScore(value, reasons, factors)

    @staticmethod
    def _capacity_fit(backend: Backend, ctx: RouterContext,
                      caps: Dict[str, Any], reasons: List[str]) -> float:
        space = len(ctx.spec.value_space())
        limits = caps.get("limits") or {}
        for key, needed in (("max_options", space), ("max_labels", space)):
            limit = limits.get(key)
            if isinstance(limit, (int, float)) and needed > limit:
                reasons.append(
                    f"{backend.name} capacity {key}={limit} < "
                    f"required {needed}: unfit")
                return 0.0
        reasons.append(f"value space of {space} fits declared limits")
        return 1.0
