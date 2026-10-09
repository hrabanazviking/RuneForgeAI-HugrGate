"""Split-conformal regression. Slice 083.

Companion to :mod:`hugrgate.calibration.conformal`: finite-sample prediction
*intervals* for real-valued predictions.  :class:`ConformalRegressor`
implements split conformal prediction with

- absolute-residual nonconformity ``s = |y − ŷ|`` (constant-width intervals), or
- normalized residuals ``s = |y − ŷ| / difficulty`` when a difficulty
  estimate is supplied (locally adaptive widths: easy points get tight
  intervals, hard points get wide ones).

Under exchangeability, ``[ŷ − q̂·d, ŷ + q̂·d]`` covers the true value with
probability at least ``1 − α``.  Operates on plain floats, so it works with
any point-prediction source, including HugrGate numeric backends.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

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

from hugrgate.errors import CalibrationError

__all__ = [
    "ConformalRegressor",
]


def _quantile(scores: np.ndarray, alpha: float) -> float:
    n = scores.size
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    k = min(n, max(1, k))
    return float(np.sort(scores)[k - 1])


class ConformalRegressor:
    """Split-conformal prediction intervals for regression."""

    def __init__(self, alpha: float = 0.1):
        if not 0.0 < alpha < 1.0:
            raise CalibrationError("alpha must be in (0, 1)")
        self.alpha = float(alpha)
        self._quantile = 0.0
        self._weighted = False
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    @property
    def quantile(self) -> float:
        self._check_fitted()
        return self._quantile

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise CalibrationError("ConformalRegressor used before fit")

    def fit(self, y_pred: Sequence[float], y_true: Sequence[float],
            difficulty: Optional[Sequence[float]] = None
            ) -> "ConformalRegressor":
        """Fit the residual quantile on a held-out calibration fold."""
        _require_numpy()
        yp = np.asarray(list(y_pred), dtype=float)
        yt = np.asarray(list(y_true), dtype=float)
        if yp.shape != yt.shape:
            raise CalibrationError("y_pred/y_true length mismatch")
        if yp.size == 0:
            raise CalibrationError("cannot fit on empty data")
        if np.any(~np.isfinite(yp)) or np.any(~np.isfinite(yt)):
            raise CalibrationError("inputs must be finite")
        resid = np.abs(yt - yp)
        if difficulty is not None:
            d = np.asarray(list(difficulty), dtype=float)
            if d.shape != yp.shape:
                raise CalibrationError("difficulty length mismatch")
            if np.any(~np.isfinite(d)) or np.any(d <= 0):
                raise CalibrationError("difficulty must be finite and positive")
            resid = resid / d
            self._weighted = True
        else:
            self._weighted = False
        self._quantile = _quantile(resid, self.alpha)
        self._fitted = True
        return self

    def predict_interval(self, y_pred: float,
                         difficulty: Optional[float] = None
                         ) -> Tuple[float, float]:
        """``(lo, hi)`` prediction interval for one point prediction."""
        self._check_fitted()
        if not math.isfinite(float(y_pred)):
            raise CalibrationError("y_pred must be finite")
        if self._weighted:
            if difficulty is None:
                raise CalibrationError(
                    "difficulty required: fitted in weighted mode")
            if not math.isfinite(difficulty) or difficulty <= 0:
                raise CalibrationError("difficulty must be finite and positive")
            half = self._quantile * float(difficulty)
        else:
            if difficulty is not None:
                raise CalibrationError(
                    "difficulty supplied but fitted unweighted")
            half = self._quantile
        yp = float(y_pred)
        return (yp - half, yp + half)

    def predict_intervals(
            self, y_pred: Sequence[float],
            difficulty: Optional[Sequence[float]] = None
    ) -> List[Tuple[float, float]]:
        preds = list(y_pred)
        diffs = ([None] * len(preds) if difficulty is None
                 else list(difficulty))
        if len(diffs) != len(preds):
            raise CalibrationError("difficulty length mismatch")
        return [self.predict_interval(p, d) for p, d in zip(preds, diffs)]

    def empirical_coverage(self, y_pred: Sequence[float],
                           y_true: Sequence[float],
                           difficulty: Optional[Sequence[float]] = None
                           ) -> float:
        intervals = self.predict_intervals(y_pred, difficulty)
        yt = list(y_true)
        if len(intervals) != len(yt):
            raise CalibrationError("length mismatch")
        hits = sum(1 for (lo, hi), y in zip(intervals, yt) if lo <= y <= hi)
        return hits / len(yt) if yt else 0.0

    def mean_width(self, y_pred: Sequence[float],
                   difficulty: Optional[Sequence[float]] = None) -> float:
        intervals = self.predict_intervals(y_pred, difficulty)
        return (sum(hi - lo for lo, hi in intervals) / len(intervals)
                if intervals else 0.0)
