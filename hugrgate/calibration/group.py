"""Group calibration. Slice 078.

A single global calibrator can hide per-group miscalibration: group A is
overconfident while group B is underconfident and the average looks fine.
:class:`GroupCalibrator` fits one binary calibrator per group value (plus a
global fallback for unseen groups), and reports per-group Brier/ECE together
with the *calibration disparity* ``max_g ECE_g − min_g ECE_g``.

Group labels are opaque strings supplied by the caller (e.g. a segment,
cohort, or backend name).  HugrGate never invents them — see the privacy
module before using real demographic attributes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

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
from hugrgate.calibration.metrics import (
    brier_score,
    expected_calibration_error,
)
from hugrgate.calibration.pipeline import validate_fit_data
from hugrgate.errors import CalibrationError

__all__ = [
    "GroupCalibrator",
]


class GroupCalibrator:
    """One calibrator per group, with a global fallback for unseen groups."""

    def __init__(self, factory: Callable[[], Calibrator],
                 min_group_samples: int = 20):
        probe = factory()
        if not isinstance(probe, Calibrator):
            raise CalibrationError("factory must return a Calibrator")
        self.factory = factory
        self.calibrator_name = probe.name
        self.min_group_samples = int(min_group_samples)
        self._units: Dict[str, Calibrator] = {}
        self._global: Optional[Calibrator] = None
        self._group_metrics: Dict[str, Dict[str, float]] = {}
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    @property
    def groups(self) -> List[str]:
        return sorted(self._units)

    @property
    def group_metrics(self) -> Dict[str, Dict[str, float]]:
        return {k: dict(v) for k, v in self._group_metrics.items()}

    def disparity(self, metric: str = "ece_after") -> float:
        """max − min of a per-group metric (the calibration fairness gap)."""
        if not self._fitted:
            raise CalibrationError("GroupCalibrator used before fit")
        vals = [m[metric] for m in self._group_metrics.values()]
        return float(max(vals) - min(vals)) if vals else 0.0

    def fit(self, scores: Sequence[float], labels: Sequence[int],
            groups: Sequence[str]) -> "GroupCalibrator":
        _require_numpy()
        scores = list(scores)
        labels = list(labels)
        groups = [str(g) for g in groups]
        if not (len(scores) == len(labels) == len(groups)):
            raise CalibrationError("scores/labels/groups length mismatch")
        if not scores:
            raise CalibrationError("cannot fit on empty data")

        # Global fallback first: always defined, used for unseen groups.
        validate_fit_data(scores, labels)
        glob = self.factory()
        glob.fit(scores, labels)
        self._global = glob

        by_group: Dict[str, Dict[str, list]] = {}
        for s, y, g in zip(scores, labels, groups):
            by_group.setdefault(g, {"scores": [], "labels": []})
            by_group[g]["scores"].append(s)
            by_group[g]["labels"].append(y)

        for g in sorted(by_group):
            gs = by_group[g]["scores"]
            gy = by_group[g]["labels"]
            if len(gs) < self.min_group_samples or sum(gy) in (0, len(gy)):
                # Too small or single-class: share the global map rather than
                # fit a degenerate per-group map.
                unit = glob
                note = "global-shared"
            else:
                validate_fit_data(gs, gy, min_samples=2)
                unit = self.factory()
                unit.fit(gs, gy)
                note = "fitted"
            self._units[g] = unit
            cal = [unit.calibrate(float(s)) for s in gs]
            self._group_metrics[g] = {
                "n": float(len(gs)),
                "brier_before": brier_score(gy, gs),
                "brier_after": brier_score(gy, cal),
                "ece_before": expected_calibration_error(gy, gs),
                "ece_after": expected_calibration_error(gy, cal),
                "mode": note,
            }
        self._fitted = True
        return self

    def _unit_for(self, group: str) -> Calibrator:
        if not self._fitted or self._global is None:
            raise CalibrationError("GroupCalibrator used before fit")
        return self._units.get(str(group), self._global)

    def calibrate(self, score: float, group: str) -> float:
        _require_numpy()
        if not np.isfinite(float(score)):
            raise CalibrationError("cannot calibrate a non-finite score")
        return self._unit_for(group).calibrate(float(score))

    def calibrate_batch(self, scores: Sequence[float],
                        groups: Sequence[str]) -> List[float]:
        scores = list(scores)
        groups = list(groups)
        if len(scores) != len(groups):
            raise CalibrationError("scores/groups length mismatch")
        return [self.calibrate(float(s), g)
                for s, g in zip(scores, groups)]

    def get_params(self) -> Dict[str, Any]:
        if not self._fitted or self._global is None:
            raise CalibrationError("GroupCalibrator used before fit")
        return {
            "calibrator_name": self.calibrator_name,
            "global": self._global.get_params(),
            "groups": {g: u.get_params() for g, u in self._units.items()},
            "group_metrics": self.group_metrics,
        }
