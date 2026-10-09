"""Isotonic regression via the Pool Adjacent Violators (PAV) algorithm.

Slice 27.  Fits a non-decreasing stepwise map from raw scores to empirical
event rates.  The PAV implementation below is written independently from the
textbook description: sort by score, greedily merge adjacent blocks whose
means violate monotonicity, and predict with the resulting step function.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

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
    "IsotonicCalibrator",
]


class IsotonicCalibrator(Calibrator):
    """Non-parametric monotone calibration (PAV)."""

    name = "isotonic"

    def __init__(self):
        super().__init__()
        self._xs: List[float] = []   # block left edges, ascending
        self._ys: List[float] = []   # block mean label (non-decreasing)
        self.n_samples = 0

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "IsotonicCalibrator":
        _require_numpy()
        s, y = self._as_arrays(scores, labels)
        n_pos = int(y.sum())
        if n_pos == 0 or n_pos == y.size:
            raise CalibrationError(
                "isotonic regression needs both classes in the fit data")

        # Sort by score (stable: ties keep input order).
        order = np.argsort(s, kind="stable")
        s_sorted = s[order]
        y_sorted = y[order]

        # Each block: (weight, sum of labels, min score).
        weights: List[float] = [1.0] * len(s_sorted)
        sums: List[float] = [float(v) for v in y_sorted]
        edges: List[float] = [float(v) for v in s_sorted]

        # Pool Adjacent Violators: merge while a block's mean exceeds the
        # next block's mean.
        i = 0
        while i < len(weights) - 1:
            if sums[i] / weights[i] > sums[i + 1] / weights[i + 1] + 1e-12:
                # Merge block i+1 into block i.
                weights[i] += weights[i + 1]
                sums[i] += sums[i + 1]
                # edges[i] already the minimum score of the merged block.
                del weights[i + 1]
                del sums[i + 1]
                del edges[i + 1]
                if i > 0:
                    i -= 1
            else:
                i += 1

        self._xs = edges
        self._ys = [sums[k] / weights[k] for k in range(len(weights))]
        self.n_samples = int(s.size)
        self._fitted = True
        return self

    def calibrate(self, score: float) -> float:
        _require_numpy()
        self._check_fitted()
        if not np.isfinite(score):
            raise CalibrationError("cannot calibrate a non-finite score")
        xs = np.asarray(self._xs)
        # Rightmost block whose left edge is <= score; clamp out-of-range
        # scores to the nearest endpoint value.
        idx = int(np.searchsorted(xs, score, side="right")) - 1
        idx = min(max(idx, 0), len(self._ys) - 1)
        return float(min(1.0, max(0.0, self._ys[idx])))

    def get_params(self) -> Dict[str, Any]:
        self._check_fitted()
        return {"xs": list(self._xs), "ys": list(self._ys),
                "n_samples": self.n_samples}

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "IsotonicCalibrator":
        obj = cls()
        obj._xs = [float(x) for x in params["xs"]]
        obj._ys = [float(v) for v in params["ys"]]
        obj.n_samples = int(params.get("n_samples", 0))
        obj._fitted = True
        return obj
