"""Probability calibration package. Slices 26-29.

Calibrators map raw classifier scores to trustworthy probabilities:

- :mod:`hugrgate.calibration.platt` — Platt scaling (sigmoid fit, independent
  Newton implementation)
- :mod:`hugrgate.calibration.isotonic` — isotonic regression (independent
  PAV implementation)
- :mod:`hugrgate.calibration.temperature` — single-parameter temperature scaling
- :mod:`hugrgate.calibration.metrics` — Brier, log loss, ECE, MCE, reliability data
- :mod:`hugrgate.calibration.profiles` — versioned calibration profiles +
  :class:`CalibratedBackend` wrapper

All calibrators are binary one-vs-rest units: ``fit(scores, labels)`` learns
the map from a score in any real range to a calibrated probability in
``[0, 1]``.  Multiclass calibration applies one unit per class and
renormalizes (see :mod:`hugrgate.calibration.profiles`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Sequence, Type

import numpy as np

from hugrgate.errors import CalibrationError


class Calibrator(ABC):
    """Maps raw classifier scores to calibrated probabilities."""

    name: str = "calibrator"

    def __init__(self):
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    @abstractmethod
    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "Calibrator":
        """Learn the calibration map. ``labels`` are 0/1."""

    @abstractmethod
    def calibrate(self, score: float) -> float:
        """Map one raw score to a calibrated probability in [0, 1]."""

    def calibrate_batch(self, scores: Sequence[float]) -> np.ndarray:
        return np.asarray([self.calibrate(float(s)) for s in scores])

    @abstractmethod
    def get_params(self) -> Dict[str, Any]:
        """JSON-serializable fitted parameters."""

    @classmethod
    @abstractmethod
    def from_params(cls, params: Dict[str, Any]) -> "Calibrator":
        """Rebuild a fitted calibrator from :meth:`get_params` output."""

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise CalibrationError(
                f"{self.name} used before fit")

    @staticmethod
    def _as_arrays(scores: Sequence[float],
                   labels: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
        s = np.asarray(list(scores), dtype=float)
        y = np.asarray(list(labels), dtype=float)
        if s.shape != y.shape:
            raise CalibrationError(
                f"scores/labels length mismatch: {s.shape} vs {y.shape}")
        if s.size == 0:
            raise CalibrationError("cannot fit on empty data")
        if np.any(~np.isfinite(s)):
            raise CalibrationError("scores must be finite")
        if not np.all(np.isin(y, (0.0, 1.0))):
            raise CalibrationError("labels must be 0/1")
        return s, y


class CalibratorRegistry:
    """Name → calibrator class registry with param-based rebuilding."""

    _registry: Dict[str, Type[Calibrator]] = {}

    @classmethod
    def register(cls, name: str, calibrator_cls: Type[Calibrator]) -> None:
        cls._registry[name] = calibrator_cls

    @classmethod
    def get(cls, name: str) -> Type[Calibrator]:
        try:
            return cls._registry[name]
        except KeyError:
            raise CalibrationError(
                f"unknown calibrator {name!r}; "
                f"known: {sorted(cls._registry)}")

    @classmethod
    def build(cls, name: str, params: Dict[str, Any]) -> Calibrator:
        return cls.get(name).from_params(params)

    @classmethod
    def list(cls) -> Dict[str, Type[Calibrator]]:
        return dict(cls._registry)


# Submodule imports come last: they reference Calibrator/CalibratorRegistry
# defined above, then register themselves here.
from hugrgate.calibration.platt import PlattCalibrator          # noqa: E402
from hugrgate.calibration.isotonic import IsotonicCalibrator    # noqa: E402
from hugrgate.calibration.temperature import (                 # noqa: E402
    TemperatureCalibrator,
)
from hugrgate.calibration import metrics, profiles              # noqa: E402

CalibratorRegistry.register("platt", PlattCalibrator)
CalibratorRegistry.register("isotonic", IsotonicCalibrator)
CalibratorRegistry.register("temperature", TemperatureCalibrator)

__all__ = [
    "Calibrator",
    "CalibratorRegistry",
    "PlattCalibrator",
    "IsotonicCalibrator",
    "TemperatureCalibrator",
    "metrics",
    "profiles",
]
