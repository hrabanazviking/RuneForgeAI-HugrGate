"""Calibration base classes (private).

Moved here from ``hugrgate.calibration.__init__`` (slice 002) so
calibrator submodules can import the base classes without creating a
parent<->child import cycle with the package ``__init__``.

Not part of the public API: import ``Calibrator`` and
``CalibratorRegistry`` from ``hugrgate.calibration`` instead.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

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
    "Calibrator",
    "CalibratorRegistry",
]


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
            labels: Sequence[int]) -> Calibrator:
        """Learn the calibration map. ``labels`` are 0/1."""

    @abstractmethod
    def calibrate(self, score: float) -> float:
        """Map one raw score to a calibrated probability in [0, 1]."""

    def calibrate_batch(self, scores: Sequence[float]) -> np.ndarray:
        _require_numpy()
        return np.asarray([self.calibrate(float(s)) for s in scores])

    @abstractmethod
    def get_params(self) -> dict[str, Any]:
        """JSON-serializable fitted parameters."""

    @classmethod
    @abstractmethod
    def from_params(cls, params: dict[str, Any]) -> Calibrator:
        """Rebuild a fitted calibrator from :meth:`get_params` output."""

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise CalibrationError(
                f"{self.name} used before fit")

    @staticmethod
    def _as_arrays(scores: Sequence[float],
                   labels: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
        _require_numpy()
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

    _registry: ClassVar[dict[str, type[Calibrator]]] = {}

    @classmethod
    def register(cls, name: str, calibrator_cls: type[Calibrator]) -> None:
        cls._registry[name] = calibrator_cls

    @classmethod
    def get(cls, name: str) -> type[Calibrator]:
        try:
            return cls._registry[name]
        except KeyError as e:
            raise CalibrationError(
                f"unknown calibrator {name!r}; "
                f"known: {sorted(cls._registry)}") from e

    @classmethod
    def build(cls, name: str, params: dict[str, Any]) -> Calibrator:
        return cls.get(name).from_params(params)

    @classmethod
    def list(cls) -> dict[str, type[Calibrator]]:
        return dict(cls._registry)


