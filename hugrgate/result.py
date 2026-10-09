"""DecisionResult — typed value + probability distribution. Slice 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "DecisionResult",
]


@dataclass
class DecisionResult:
    """The outcome of a HugrGate decision.

    Invariants:
    - probability ∈ [0, 1]
    - distribution keys ⊆ spec value space, values ∈ [0,1], sum ≈ 1
    - value ∈ spec value space (or None for abstention)
    """
    value: Any | None
    probability: float
    distribution: dict[str, float] = field(default_factory=dict)
    uncertainty: float = 0.0
    accepted: bool = True
    backend: str = "unknown"
    model: str = "unknown"
    latency_ms: float = 0.0
    calibration_profile: str = "none"
    fallback_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.probability <= 1.0:
            raise SpecError(f"probability out of bounds: {self.probability}")
        if not 0.0 <= self.uncertainty <= 1.0:
            raise SpecError(f"uncertainty out of bounds: {self.uncertainty}")
        if self.latency_ms < 0:
            raise SpecError(f"latency_ms must be >= 0: {self.latency_ms}")
        if self.distribution:
            total = sum(self.distribution.values())
            if abs(total - 1.0) > 1e-6:
                raise SpecError(
                    f"distribution must sum to 1, got {total}")
            for k, v in self.distribution.items():
                if not isinstance(k, str) or not k:
                    raise SpecError(
                        f"distribution keys must be non-empty strings, "
                        f"got {k!r}")
                if not 0.0 <= v <= 1.0:
                    raise SpecError(
                        f"distribution[{k!r}] out of bounds: {v}")
            # The chosen value's mass must equal the reported probability:
            # otherwise the result contradicts itself. (Multilabel values
            # are lists of labels; each label carries its own mass, so the
            # equality check applies to single-value results only.)
            if (self.value is not None
                    and not isinstance(self.value, list)
                    and self.value in self.distribution):
                mass = self.distribution[self.value]
                if abs(mass - self.probability) > 1e-6:
                    raise SpecError(
                        f"distribution[{self.value!r}]={mass} != "
                        f"probability={self.probability}")

    def to_dict(self) -> dict[str, Any]:
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
