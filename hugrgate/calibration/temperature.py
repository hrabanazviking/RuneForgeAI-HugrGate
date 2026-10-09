"""Temperature scaling. Slice 27.

Single-parameter calibration: ``p_cal = σ(logit(p_raw) / T)`` with ``T > 0``
fit by minimizing the negative log-likelihood with an independent 1-D
Newton solver in ``u = log T`` space.  Because ``T > 0``, the map is strictly
increasing — the ranking of scores is always preserved.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

import numpy as np

from hugrgate.calibration import Calibrator
from hugrgate.errors import CalibrationError

_EPS = 1e-12


def _sigmoid(x: np.ndarray) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    ex = np.exp(x[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out


class TemperatureCalibrator(Calibrator):
    """Single-parameter temperature scaling (independent Newton solver).

    Fits ``T`` on probability scores; ``calibrate`` accepts a raw
    probability, converts to a logit, divides by ``T``, and maps back.
    """

    name = "temperature"

    def __init__(self, max_iter: int = 100, tol: float = 1e-10):
        super().__init__()
        self.max_iter = max_iter
        self.tol = tol
        self.temperature = 1.0
        self.n_samples = 0

    @staticmethod
    def _clip(p: np.ndarray) -> np.ndarray:
        return np.clip(p, _EPS, 1.0 - _EPS)

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "TemperatureCalibrator":
        p_raw, y = self._as_arrays(scores, labels)
        if int(y.sum()) == 0 or int(y.sum()) == y.size:
            raise CalibrationError(
                "temperature scaling needs both classes in the fit data")
        z = np.log(self._clip(p_raw) / (1.0 - self._clip(p_raw)))  # logits

        def nll(u: float) -> float:
            q = _sigmoid(z * np.exp(-u))
            qc = self._clip(q)
            return float(-(y * np.log(qc) + (1.0 - y) * np.log(1.0 - qc)).sum())

        # Newton in u = log T.  With q = σ(z·e^{-u}) and w = z·e^{-u}:
        #   g = dNLL/du = Σ (y - q)·w
        #   H = d²NLL/du² = Σ [q(1-q)·w² - (y-q)·w]
        u = 0.0
        current = nll(u)
        for _ in range(self.max_iter):
            e = np.exp(-u)
            w = z * e
            q = _sigmoid(w)
            g = float(np.sum((y - q) * w))
            h = float(np.sum(q * (1.0 - q) * w * w - (y - q) * w))
            if abs(h) < 1e-14:
                break
            step = g / h
            # Backtrack so the NLL never increases; keep T in a sane range.
            trial = min(6.0, max(-6.0, u - step))
            trial_nll = nll(trial)
            shrink = 0
            while trial_nll > current and shrink < 20:
                trial = (u + trial) / 2.0
                trial_nll = nll(trial)
                shrink += 1
            u, current = trial, trial_nll
            if abs(step) < self.tol:
                break

        self.temperature = float(np.exp(u))
        self.n_samples = int(p_raw.size)
        self._fitted = True
        return self

    def calibrate(self, score: float) -> float:
        self._check_fitted()
        if not np.isfinite(score):
            raise CalibrationError("cannot calibrate a non-finite score")
        p = float(self._clip(np.array([score]))[0])
        z = np.log(p / (1.0 - p))
        q = float(_sigmoid(np.array([z / self.temperature]))[0])
        return min(1.0, max(0.0, q))

    def get_params(self) -> Dict[str, Any]:
        self._check_fitted()
        return {"temperature": self.temperature,
                "n_samples": self.n_samples}

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "TemperatureCalibrator":
        obj = cls()
        obj.temperature = float(params["temperature"])
        if obj.temperature <= 0:
            raise CalibrationError("temperature must be positive")
        obj.n_samples = int(params.get("n_samples", 0))
        obj._fitted = True
        return obj
