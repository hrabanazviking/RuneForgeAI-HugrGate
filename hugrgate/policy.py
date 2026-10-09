"""DecisionPolicy — application-controlled thresholds. Slice 5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from hugrgate.errors import PolicyError
from hugrgate.result import DecisionResult

__all__ = [
    "DecisionPolicy",
]


@dataclass
class DecisionPolicy:
    """Thresholds belong to the application, not the model."""
    minimum_probability: float = 0.0
    maximum_latency_ms: Optional[float] = None
    remote_inference: bool = False
    allowed_backends: Optional[List[str]] = None
    preferred_backends: Optional[List[str]] = None
    fallback_behavior: str = "abstain"  # abstain|safe_default|escalate
    privacy_class: str = "standard"     # standard|strict
    max_cost: Optional[float] = None
    review_band: Optional[tuple] = None  # (low, high) → "review"

    #: The only privacy classes with defined semantics. Anything else is
    #: a typo, not a new class — rejected loudly (slice 008), because a
    #: misspelled "strict" must never silently degrade to "standard".
    PRIVACY_CLASSES = ("standard", "strict")

    def __post_init__(self):
        if not 0.0 <= self.minimum_probability <= 1.0:
            raise PolicyError("minimum_probability must be in [0,1]")
        if self.fallback_behavior not in ("abstain", "safe_default", "escalate"):
            raise PolicyError(
                f"unknown fallback_behavior: {self.fallback_behavior}")
        if self.privacy_class not in self.PRIVACY_CLASSES:
            raise PolicyError(
                f"unknown privacy_class: {self.privacy_class!r}; "
                f"expected one of {list(self.PRIVACY_CLASSES)}")
        if self.maximum_latency_ms is not None and self.maximum_latency_ms <= 0:
            raise PolicyError("maximum_latency_ms must be > 0")
        if self.max_cost is not None and self.max_cost < 0:
            raise PolicyError("max_cost must be >= 0")
        if self.review_band:
            lo, hi = self.review_band
            if not 0.0 <= lo <= hi <= 1.0:
                raise PolicyError("review_band must be within [0,1]")

    def evaluate(self, result: DecisionResult) -> str:
        """Return 'accept', 'review', or 'abstain'."""
        if self.maximum_latency_ms is not None:
            if result.latency_ms > self.maximum_latency_ms:
                return "abstain"
        p = result.probability
        if p < self.minimum_probability:
            return "abstain"
        if self.review_band:
            lo, hi = self.review_band
            if lo <= p < hi:
                return "review"
        return "accept"

    def backend_allowed(self, backend_name: str, is_remote: bool) -> bool:
        if is_remote and not self.remote_inference:
            return False
        if self.allowed_backends is not None:
            return backend_name in self.allowed_backends
        return True
