"""Bayesian calibration research adapter. Slice 081.

RESEARCH ADAPTER — not a production default.  :class:`BetaBinomialCalibrator`
treats each score bin as a Binomial experiment with a Beta prior and returns
the posterior predictive mean as the calibrated probability, *plus* a
credible interval so downstream code can see how much data backs the map.
Useful for low-data regimes and for studying prior sensitivity; prefer
Platt/isotonic/temperature when you have ample data and want a point map.

The Beta quantiles use an independent implementation of the regularized
incomplete beta function (continued fraction, Numerical Recipes ``betacf``)
with bisection inversion — no scipy dependency.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

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

from hugrgate.calibration._base import Calibrator
from hugrgate.errors import CalibrationError

__all__ = [
    "BetaBinomialCalibrator",
    "beta_quantile",
]


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function."""
    max_iter, eps, fpmin = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = fpmin if abs(d) < fpmin else d
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1.0 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = fpmin if abs(d) < fpmin else d
        c = 1.0 + aa / c
        c = fpmin if abs(c) < fpmin else c
        d = 1.0 / d
        delta = c * d
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if not (0.0 <= x <= 1.0):
        raise ValueError("x must be in [0, 1]")
    if x in (0.0, 1.0):
        return x
    if a <= 0 or b <= 0:
        raise ValueError("a and b must be positive")
    log_beta = (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - log_beta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_quantile(p: float, a: float, b: float, tol: float = 1e-10) -> float:
    """Inverse regularized incomplete beta (bisection)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _betai(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2.0


class BetaBinomialCalibrator(Calibrator):
    """Per-bin Beta-Binomial posterior calibration (research adapter)."""

    name = "beta-binomial"

    def __init__(self, n_bins: int = 10, prior_a: float = 1.0,
                 prior_b: float = 1.0):
        super().__init__()
        if n_bins < 2:
            raise CalibrationError("n_bins must be ≥ 2")
        if prior_a <= 0 or prior_b <= 0:
            raise CalibrationError("Beta prior parameters must be positive")
        self.n_bins = int(n_bins)
        self.prior_a = float(prior_a)
        self.prior_b = float(prior_b)
        self._pos: List[float] = [0.0] * self.n_bins
        self._tot: List[float] = [0.0] * self.n_bins

    def _bin(self, score: float) -> int:
        b = int(score * self.n_bins)
        return min(self.n_bins - 1, max(0, b))

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "BetaBinomialCalibrator":
        s, y = self._as_arrays(scores, labels)
        self._pos = [0.0] * self.n_bins
        self._tot = [0.0] * self.n_bins
        for score, label in zip(s.tolist(), y.tolist()):
            b = self._bin(min(1.0, max(0.0, score)))
            self._tot[b] += 1.0
            self._pos[b] += label
        self._fitted = True
        return self

    def _posterior(self, score: float) -> Tuple[float, float]:
        b = self._bin(min(1.0, max(0.0, float(score))))
        return (self.prior_a + self._pos[b], self.prior_b + self._tot[b] - self._pos[b])

    def calibrate(self, score: float) -> float:
        _require_numpy()
        self._check_fitted()
        if not np.isfinite(float(score)):
            raise CalibrationError("cannot calibrate a non-finite score")
        a, b = self._posterior(float(score))
        return float(a / (a + b))

    def credible_interval(self, score: float,
                          level: float = 0.9) -> Tuple[float, float]:
        """Equal-tailed ``level`` credible interval for the bin's true rate."""
        self._check_fitted()
        if not 0.0 < level < 1.0:
            raise CalibrationError("level must be in (0, 1)")
        a, b = self._posterior(float(score))
        tail = (1.0 - level) / 2.0
        return (beta_quantile(tail, a, b), beta_quantile(1.0 - tail, a, b))

    def get_params(self) -> Dict[str, Any]:
        self._check_fitted()
        return {
            "n_bins": self.n_bins,
            "prior_a": self.prior_a,
            "prior_b": self.prior_b,
            "positives": list(self._pos),
            "totals": list(self._tot),
        }

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "BetaBinomialCalibrator":
        obj = cls(n_bins=int(params["n_bins"]),
                  prior_a=float(params["prior_a"]),
                  prior_b=float(params["prior_b"]))
        obj._pos = [float(v) for v in params["positives"]]
        obj._tot = [float(v) for v in params["totals"]]
        if len(obj._pos) != obj.n_bins:
            raise CalibrationError("bin arrays do not match n_bins")
        obj._fitted = True
        return obj
