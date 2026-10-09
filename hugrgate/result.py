"""DecisionResult — typed value + probability distribution. Slice 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from hugrgate.errors import SpecError


@dataclass
class DecisionResult:
    """The outcome of a HugrGate decision.

    Invariants:
    - probability ∈ [0, 1]
    - distribution keys ⊆ spec value space, values ∈ [0,1], sum ≈ 1
    - value ∈ spec value space (or None for abstention)
    """
    value: Optional[Any]
    probability: float
    distribution: Dict[str, float] = field(default_factory=dict)
    uncertainty: float = 0.0
    accepted: bool = True
    backend: str = "unknown"
    model: str = "unknown"
    latency_ms: float = 0.0
    calibration_profile: str = "none"
    fallback_used: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.probability <= 1.0:
            raise SpecError(f"probability out of bounds: {self.probability}")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise SpecError(f"uncertainty out of bounds: {self.uncertainty}")
        if self.distribution:
            total = sum(self.distribution.values())
            if abs(total - 1.0) > 1e-6:
                raise SpecError(
                    f"distribution must sum to 1, got {total}")
            for k, v in self.distribution.items():
                if not 0.0 <= v <= 1.0:
                    raise SpecError(
                        f"distribution[{k!r}] out of bounds: {v}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "probability": self.probability,
            "distribution": dict(self.distribution),
            "uncertainty": self.uncertainty,
            "accepted": self.accepted,
            "backend": self.backend,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "calibration_profile": self.calibration_profile,
            "fallback_used": self.fallback_used,
            "metadata": dict(self.metadata),
        }
