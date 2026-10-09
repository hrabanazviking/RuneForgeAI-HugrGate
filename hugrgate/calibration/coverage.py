"""Coverage guarantees tooling. Slice 085.

Conformal prediction promises *marginal* coverage ≥ 1−α, but on any finite
test set the empirical hit rate is just an estimate.  This module turns that
estimate into a checkable claim:

- :func:`clopper_pearson` — exact two-sided binomial confidence interval
  (built on the slice-081 ``beta_quantile``, no scipy);
- :func:`hoeffding_lower_bound` — one-sided Hoeffding lower bound, the
  distribution-free quick check;
- :class:`CoverageCertificate` — bundles n, hits, empirical coverage, the
  interval, and a ``holds`` verdict against a target coverage;
- :func:`validate_coverage` — certify a batch of
  :class:`~hugrgate.calibration.sets.PredictionSet` outcomes;
- :func:`required_n` — how many test points you need before a
  Clopper-Pearson interval of a given width is even possible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Sequence, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]


def _require_numpy() -> None:
    """Deliberate error when the optional numpy dependency is absent."""
    if np is None:  # pragma: no cover - optional dependency
        raise CalibrationError(
            "numpy is required for calibration; install the 'ml' extra: pip install 'hugrgate[ml]'"
        )

from hugrgate.calibration.bayes import beta_quantile
from hugrgate.errors import CalibrationError

__all__ = [
    "clopper_pearson",
    "hoeffding_lower_bound",
    "CoverageCertificate",
    "validate_coverage",
    "required_n",
]


def clopper_pearson(k: int, n: int, level: float = 0.95
                    ) -> Tuple[float, float]:
    """Exact two-sided binomial confidence interval for the hit rate."""
    if n <= 0:
        raise CalibrationError("n must be positive")
    if not 0 <= k <= n:
        raise CalibrationError("k must satisfy 0 ≤ k ≤ n")
    if not 0.0 < level < 1.0:
        raise CalibrationError("level must be in (0, 1)")
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else beta_quantile(tail, k, n - k + 1)
    hi = 1.0 if k == n else beta_quantile(1.0 - tail, k + 1, n - k)
    return (lo, hi)


def hoeffding_lower_bound(k: int, n: int, delta: float = 0.05) -> float:
    """One-sided lower bound: P(true rate ≥ bound) ≥ 1 − δ."""
    if n <= 0:
        raise CalibrationError("n must be positive")
    if not 0 <= k <= n:
        raise CalibrationError("k must satisfy 0 ≤ k ≤ n")
    if not 0.0 < delta < 1.0:
        raise CalibrationError("delta must be in (0, 1)")
    return max(0.0, k / n - math.sqrt(math.log(1.0 / delta) / (2.0 * n)))


@dataclass
class CoverageCertificate:
    """A checkable coverage claim for one batch of prediction sets."""

    n: int
    hits: int
    level: float = 0.95
    method: str = "clopper-pearson"
    notes: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.n <= 0:
            raise CalibrationError("n must be positive")
        if not 0 <= self.hits <= self.n:
            raise CalibrationError("hits must satisfy 0 ≤ hits ≤ n")

    @property
    def empirical(self) -> float:
        return self.hits / self.n

    def interval(self) -> Tuple[float, float]:
        if self.method == "clopper-pearson":
            return clopper_pearson(self.hits, self.n, self.level)
        if self.method == "hoeffding":
            return (hoeffding_lower_bound(self.hits, self.n,
                                          1.0 - self.level), 1.0)
        raise CalibrationError(f"unknown method {self.method!r}")

    def validates(self, target: float) -> bool:
        """True when the interval's lower end clears the target coverage."""
        lo, _ = self.interval()
        return lo >= target

    def as_dict(self) -> Dict[str, Any]:
        lo, hi = self.interval()
        return {
            "n": self.n,
            "hits": self.hits,
            "empirical": self.empirical,
            "level": self.level,
            "method": self.method,
            "interval": [lo, hi],
            "notes": self.notes,
            "extra": dict(self.extra),
        }


def validate_coverage(sets: Sequence[Any], labels: Sequence[str],
                      target: float, level: float = 0.95,
                      method: str = "clopper-pearson") -> CoverageCertificate:
    """Certify prediction-set outcomes against a target coverage."""
    sets = list(sets)
    labels = list(labels)
    if len(sets) != len(labels):
        raise CalibrationError("sets/labels length mismatch")
    if not sets:
        raise CalibrationError("empty set batch")
    if not 0.0 < target < 1.0:
        raise CalibrationError("target must be in (0, 1)")
    hits = sum(1 for s, y in zip(sets, labels) if s.covers(y))
    cert = CoverageCertificate(n=len(sets), hits=hits, level=level,
                               method=method,
                               notes=f"target coverage {target}",
                               extra={"target": target})
    cert.extra["holds"] = cert.validates(target)
    return cert


def required_n(width: float, level: float = 0.95,
               p: float = 0.5) -> int:
    """Smallest n whose worst-case Clopper-Pearson width ≤ ``width``.

    Uses the normal-approximation upper bound on the CP width
    (conservative), binary-searched.
    """
    if not 0.0 < width < 1.0:
        raise CalibrationError("width must be in (0, 1)")
    if not 0.0 < level < 1.0:
        raise CalibrationError("level must be in (0, 1)")
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1.0 - (1.0 - level) / 2.0)
    # Normal approx width ≈ 2·z·√(p(1−p)/n) ≥ CP width near p=0.5 worst case.
    lo, hi = 1, 10 ** 9
    while lo < hi:
        mid = (lo + hi) // 2
        w = 2.0 * z * math.sqrt(0.25 / mid)
        if w <= width:
            hi = mid
        else:
            lo = mid + 1
    return lo
