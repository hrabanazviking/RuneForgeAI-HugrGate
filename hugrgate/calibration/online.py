"""Online (incremental) calibration. Slice 079.

Batch calibrators assume the world stands still while you collect a fit set.
:class:`OnlineCalibrator` instead maintains binned (score → empirical rate)
statistics that update with every :meth:`partial_fit` call and slowly forget
old data via exponential decay, so the map tracks a drifting relationship
between scores and outcomes.

- Each of ``n_bins`` bins keeps decayed ``(positives, total)`` counts.
- The calibrated value for a score is the Laplace-smoothed empirical rate
  of its bin, passed through a weighted pool-adjacent-violators (PAV) pass
  so the map stays monotone non-decreasing in the score.
- ``decay=1.0`` disables forgetting (pure cumulative counts);
  ``decay<1.0`` down-weights older batches per :meth:`partial_fit` call.

It subclasses :class:`Calibrator` (``fit`` = reset + one ``partial_fit``)
so it works with the pipeline, registry, and auto-selection.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

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
    "OnlineCalibrator",
]


def _pav_weighted(rates: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted isotonic regression (PAV); returns monotone rates."""
    n = len(rates)
    # Each block: (sum_w, sum_wr, start, end).
    sum_w = list(weights)
    sum_wr = list(weights * rates)
    starts = list(range(n))
    ends = list(range(n))
    i = 0
    while i < len(sum_w) - 1:
        m1 = sum_wr[i] / sum_w[i] if sum_w[i] > 0 else 0.0
        m2 = sum_wr[i + 1] / sum_w[i + 1] if sum_w[i + 1] > 0 else 0.0
        if m1 <= m2:
            i += 1
        else:
            sum_w[i] += sum_w[i + 1]
            sum_wr[i] += sum_wr[i + 1]
            ends[i] = ends[i + 1]
            del sum_w[i + 1]
            del sum_wr[i + 1]
            del starts[i + 1]
            del ends[i + 1]
            if i > 0:
                i -= 1
    out = np.empty(n)
    for sw, swr, a, b in zip(sum_w, sum_wr, starts, ends, strict=True):
        out[a: b + 1] = swr / sw if sw > 0 else 0.0
    return out


class OnlineCalibrator(Calibrator):
    """Incremental binned calibration with exponential forgetting."""

    name = "online"

    def __init__(self, n_bins: int = 10, decay: float = 0.995,
                 prior_strength: float = 1.0):
        super().__init__()
        if n_bins < 2:
            raise CalibrationError("n_bins must be ≥ 2")
        if not 0.0 < decay <= 1.0:
            raise CalibrationError("decay must be in (0, 1]")
        if prior_strength < 0:
            raise CalibrationError("prior_strength must be ≥ 0")
        self.n_bins = int(n_bins)
        self.decay = float(decay)
        self.prior_strength = float(prior_strength)
        self._pos: list[float] = [0.0] * self.n_bins
        self._tot: list[float] = [0.0] * self.n_bins
        self._n_updates = 0

    def _bin(self, score: float) -> int:
        b = int(score * self.n_bins)
        return min(self.n_bins - 1, max(0, b))

    def partial_fit(self, scores: Sequence[float],
                    labels: Sequence[int]) -> OnlineCalibrator:
        """Incorporate one batch; old batches decay by ``self.decay``."""
        s, y = self._as_arrays(scores, labels)
        if self._n_updates:
            self._pos = [v * self.decay for v in self._pos]
            self._tot = [v * self.decay for v in self._tot]
        for score, label in zip(s.tolist(), y.tolist(), strict=True):
            b = self._bin(min(1.0, max(0.0, score)))
            self._tot[b] += 1.0
            self._pos[b] += label
        self._n_updates += 1
        self._fitted = True
        return self

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> OnlineCalibrator:
        self._pos = [0.0] * self.n_bins
        self._tot = [0.0] * self.n_bins
        self._n_updates = 0
        self._fitted = False
        return self.partial_fit(scores, labels)

    def _rates(self) -> np.ndarray:
        _require_numpy()
        pos = np.array(self._pos)
        tot = np.array(self._tot)
        a = self.prior_strength
        # Laplace-smoothed empirical rate, prior centered at the bin midpoint.
        centers = (np.arange(self.n_bins) + 0.5) / self.n_bins
        smoothed = (pos + a * centers) / (tot + a)
        return _pav_weighted(smoothed, tot + 1e-9)

    def calibrate(self, score: float) -> float:
        _require_numpy()
        self._check_fitted()
        if not np.isfinite(float(score)):
            raise CalibrationError("cannot calibrate a non-finite score")
        rates = self._rates()
        return float(min(1.0, max(0.0, rates[self._bin(min(1.0, max(0.0, float(score))))])))

    def effective_samples(self) -> float:
        """Total decayed weight — how much history is still 'alive'."""
        return float(sum(self._tot))

    def bin_stats(self) -> list[dict[str, float]]:
        self._check_fitted()
        rates = self._rates()
        return [
            {"bin": float(i),
             "weight": float(self._tot[i]),
             "positives": float(self._pos[i]),
             "rate": float(rates[i])}
            for i in range(self.n_bins)
        ]

    def get_params(self) -> dict[str, Any]:
        self._check_fitted()
        return {
            "n_bins": self.n_bins,
            "decay": self.decay,
            "prior_strength": self.prior_strength,
            "positives": list(self._pos),
            "totals": list(self._tot),
            "n_updates": self._n_updates,
        }

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> OnlineCalibrator:
        obj = cls(n_bins=int(params["n_bins"]),
                  decay=float(params["decay"]),
                  prior_strength=float(params.get("prior_strength", 1.0)))
        obj._pos = [float(v) for v in params["positives"]]
        obj._tot = [float(v) for v in params["totals"]]
        if len(obj._pos) != obj.n_bins or len(obj._tot) != obj.n_bins:
            raise CalibrationError("bin arrays do not match n_bins")
        obj._n_updates = int(params.get("n_updates", 0))
        obj._fitted = True
        return obj
