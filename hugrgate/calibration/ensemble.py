"""Calibration ensemble. Slice 093.

No single calibrator wins everywhere: Platt is stable but rigid, isotonic
is flexible but data-hungry, temperature is minimal.  :class:`CalibratorEnsemble`
fits several member calibrators on the same data and averages their maps —
mean (default), median, or custom weights.

By Jensen's inequality the Brier score of a convex combination is at most
the average of the members' Brier scores, so the ensemble never pays more
than the *average* member — and in practice it lands near the best one
without requiring the choice up front (see also slice 092's auto-selection).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Tuple

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

from hugrgate.calibration._base import Calibrator, CalibratorRegistry
from hugrgate.calibration.isotonic import IsotonicCalibrator
from hugrgate.calibration.platt import PlattCalibrator
from hugrgate.calibration.temperature import TemperatureCalibrator
from hugrgate.errors import CalibrationError

__all__ = [
    "CalibratorEnsemble",
]


class CalibratorEnsemble(Calibrator):
    """Weighted average of several fitted calibrator maps."""

    name = "ensemble"

    def __init__(self,
                 members: Sequence[Tuple[Callable[[], Calibrator], float]]
                 | None = None,
                 mode: str = "mean"):
        super().__init__()
        if mode not in ("mean", "median"):
            raise CalibrationError("mode must be 'mean' or 'median'")
        self.mode = mode
        self._spec: List[Tuple[Callable[[], Calibrator], float]] = []
        if members is None:
            # Default: the three classic point calibrators, uniform weights.
            members = [(PlattCalibrator, 1.0), (IsotonicCalibrator, 1.0),
                       (TemperatureCalibrator, 1.0)]
        for factory, weight in members:
            probe = factory()
            if not isinstance(probe, Calibrator):
                raise CalibrationError(
                    "member factory must return a Calibrator")
            if weight < 0:
                raise CalibrationError("weights must be non-negative")
            self._spec.append((factory, float(weight)))
        if self._spec and sum(w for _, w in self._spec) <= 0:
            raise CalibrationError("weights must sum to something positive")
        self._members: List[Calibrator] = []
        self._weights: List[float] = []

    @property
    def member_names(self) -> List[str]:
        return [m.name for m in self._members]

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "CalibratorEnsemble":
        s, y = self._as_arrays(scores, labels)
        self._members = []
        for factory, _ in self._spec:
            cal = factory()
            cal.fit(s.tolist(), y.tolist())
            self._members.append(cal)
        total = sum(w for _, w in self._spec)
        self._weights = [w / total for _, w in self._spec]
        self._fitted = True
        return self

    def calibrate(self, score: float) -> float:
        _require_numpy()
        self._check_fitted()
        if not np.isfinite(float(score)):
            raise CalibrationError("cannot calibrate a non-finite score")
        vals = np.array([m.calibrate(float(score)) for m in self._members])
        if self.mode == "median":
            out = float(np.median(vals))
        else:
            out = float(np.dot(vals, np.asarray(self._weights)))
        return min(1.0, max(0.0, out))

    def member_spread(self, score: float) -> float:
        """Max − min member output: disagreement at one score."""
        self._check_fitted()
        vals = [m.calibrate(float(score)) for m in self._members]
        return float(max(vals) - min(vals))

    def get_params(self) -> Dict[str, Any]:
        self._check_fitted()
        return {
            "mode": self.mode,
            "members": [{"name": m.name, "params": m.get_params()}
                        for m in self._members],
            "weights": list(self._weights),
        }

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "CalibratorEnsemble":
        members = params["members"]
        weights = params.get("weights", [1.0] * len(members))
        if len(members) != len(weights):
            raise CalibrationError("members/weights length mismatch")
        obj = cls(mode=params.get("mode", "mean"))
        obj._members = []
        for entry, w in zip(members, weights):
            cal = CalibratorRegistry.build(entry["name"], entry["params"])
            obj._members.append(cal)
        total = sum(float(w) for w in weights)
        if total <= 0:
            raise CalibrationError("weights must sum to something positive")
        obj._weights = [float(w) / total for w in weights]
        obj._fitted = True
        return obj
