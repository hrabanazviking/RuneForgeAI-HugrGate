"""Platt scaling. Slice 26.

Fits a sigmoid ``p = 1 / (1 + exp(A·s + B))`` to validation scores by
minimizing the negative log-likelihood with Platt's target smoothing.
The Newton optimization below is an independent implementation written
from the textbook formulation (gradient/Hessian of the logistic loss);
no code is copied from scikit-learn or any other library.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

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
    "PlattCalibrator",
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    # Numerically stable logistic function.
    _require_numpy()
    out = np.empty_like(x, dtype=float)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    ex = np.exp(x[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out


class PlattCalibrator(Calibrator):
    """Sigmoid (Platt) calibration with an independent Newton solver.

    Parameters ``A`` and ``B`` minimize
    ``-Σ [tᵢ log pᵢ + (1-tᵢ) log(1-pᵢ)]`` where ``pᵢ = σ(A·sᵢ + B)`` and the
    targets ``tᵢ`` use Platt's smoothing: ``(N₊+1)/(N₊+2)`` for positives,
    ``1/(N₋+2)`` for negatives.  Newton updates solve ``H·δ = g`` for the
    gradient ``g`` and Hessian ``H`` derived below.
    """

    name = "platt"

    def __init__(self, max_iter: int = 100, tol: float = 1e-10):
        super().__init__()
        self.max_iter = max_iter
        self.tol = tol
        self.A = 0.0
        self.B = 0.0
        self.n_samples = 0

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "PlattCalibrator":
        _require_numpy()
        s, y = self._as_arrays(scores, labels)
        n_pos = int(y.sum())
        n_neg = int(y.size - n_pos)
        if n_pos == 0 or n_neg == 0:
            raise CalibrationError(
                "Platt scaling needs both classes in the fit data")

        # Platt's smoothed targets.
        t = np.where(y == 1.0,
                     (n_pos + 1.0) / (n_pos + 2.0),
                     1.0 / (n_neg + 2.0))

        # Initial guess: A=0, B = prior log-odds of the positive class.
        theta = np.array([0.0, np.log((n_neg + 1.0) / (n_pos + 1.0))])

        for _ in range(self.max_iter):
            z = theta[0] * s + theta[1]
            p = _sigmoid(z)
            r = p - t  # residuals
            # Gradient of the NLL.
            g = np.array([np.dot(r, s), r.sum()])
            # Hessian of the NLL: H = Σ p(1-p) · [[s², s], [s, 1]].
            w = p * (1.0 - p)
            h_ss = float(np.dot(w, s * s))
            h_sb = float(np.dot(w, s))
            h_bb = float(w.sum())
            H = np.array([[h_ss, h_sb], [h_sb, h_bb]])
            # Tiny ridge keeps the solve stable for constant scores.
            H += np.eye(2) * 1e-10 * max(1.0, np.trace(H))
            try:
                step = np.linalg.solve(H, g)
            except np.linalg.LinAlgError:
                step, *_ = np.linalg.lstsq(H, g, rcond=None)
            theta = theta - step
            if float(np.dot(step, step)) < self.tol ** 2:
                break

        self.A, self.B = float(theta[0]), float(theta[1])
        self.n_samples = int(s.size)
        self._fitted = True
        return self

    def calibrate(self, score: float) -> float:
        _require_numpy()
        self._check_fitted()
        if not np.isfinite(score):
            raise CalibrationError("cannot calibrate a non-finite score")
        p = float(_sigmoid(np.array([self.A * score + self.B]))[0])
        return min(1.0, max(0.0, p))

    def get_params(self) -> Dict[str, Any]:
        self._check_fitted()
        return {"A": self.A, "B": self.B, "n_samples": self.n_samples}

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "PlattCalibrator":
        obj = cls()
        obj.A = float(params["A"])
        obj.B = float(params["B"])
        obj.n_samples = int(params.get("n_samples", 0))
        obj._fitted = True
        return obj
