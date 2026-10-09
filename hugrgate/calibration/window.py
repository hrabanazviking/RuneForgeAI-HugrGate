"""Sliding-window calibration. Slice 080.

Complements the binned :class:`OnlineCalibrator` (slice 079): instead of an
approximate incremental map, :class:`SlidingWindowCalibrator` keeps the last
``window_size`` raw ``(score, label)`` pairs and periodically *refits* any
ordinary batch calibrator on exactly that window.  You get the full fidelity
of Platt/isotonic/temperature on recent data, at the cost of a refit per
``refit_every`` samples.

A refit is attempted only when the window holds at least ``min_samples``
rows with both classes present; otherwise the previous map is kept (or, if
no fit ever succeeded, :meth:`calibrate` raises).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Tuple

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
    "SlidingWindowCalibrator",
]


class SlidingWindowCalibrator(Calibrator):
    """Refit-any-calibrator on a sliding window of recent (score, label)s."""

    name = "sliding-window"

    def __init__(self, factory: Callable[[], Calibrator],
                 window_size: int = 500,
                 refit_every: int = 50,
                 min_samples: int = 20):
        super().__init__()
        probe = factory()
        if not isinstance(probe, Calibrator):
            raise CalibrationError("factory must return a Calibrator")
        if window_size < 2:
            raise CalibrationError("window_size must be ≥ 2")
        if refit_every < 1:
            raise CalibrationError("refit_every must be ≥ 1")
        self.factory = factory
        self.inner_name = probe.name
        self.window_size = int(window_size)
        self.refit_every = int(refit_every)
        self.min_samples = int(min_samples)
        self._window: Deque[Tuple[float, int]] = deque(maxlen=window_size)
        self._inner: Optional[Calibrator] = None
        self._since_refit = 0
        self.refit_count = 0

    # -- streaming -----------------------------------------------------
    def partial_fit(self, scores: Sequence[float],
                    labels: Sequence[int]) -> "SlidingWindowCalibrator":
        s, y = self._as_arrays(scores, labels)
        for score, label in zip(s.tolist(), y.tolist()):
            self._window.append((float(score), int(label)))
            self._since_refit += 1
        if self._since_refit >= self.refit_every:
            self.refit()
        return self

    def refit(self) -> bool:
        """Refit on the current window. Returns True if a fit succeeded."""
        self._since_refit = 0
        if len(self._window) < self.min_samples:
            return False
        scores = [s for s, _ in self._window]
        labels = [y for _, y in self._window]
        if sum(labels) in (0, len(labels)):
            return False  # single-class window: keep the old map
        inner = self.factory()
        inner.fit(scores, labels)
        self._inner = inner
        self.refit_count += 1
        self._fitted = True
        return True

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "SlidingWindowCalibrator":
        self._window.clear()
        self._inner = None
        self._since_refit = 0
        self.refit_count = 0
        self._fitted = False
        self.partial_fit(scores, labels)
        self.refit()  # fit() must leave a usable map or raise
        if self._inner is None:
            raise CalibrationError(
                "sliding-window fit data unusable "
                f"(need ≥{self.min_samples} samples with both classes)")
        return self

    # -- serving --------------------------------------------------------
    def calibrate(self, score: float) -> float:
        _require_numpy()
        self._check_fitted()
        if not np.isfinite(float(score)):
            raise CalibrationError("cannot calibrate a non-finite score")
        assert self._inner is not None
        return self._inner.calibrate(float(score))

    @property
    def window_fill(self) -> int:
        return len(self._window)

    @property
    def window_span(self) -> Optional[Tuple[float, float]]:
        if not self._window:
            return None
        ss = [s for s, _ in self._window]
        return (min(ss), max(ss))

    # -- persistence ------------------------------------------------------
    def get_params(self) -> Dict[str, Any]:
        self._check_fitted()
        assert self._inner is not None
        return {
            "factory_calibrator": self.inner_name,
            "window_size": self.window_size,
            "refit_every": self.refit_every,
            "min_samples": self.min_samples,
            "inner_params": self._inner.get_params(),
            "window": [[s, y] for s, y in self._window],
            "refit_count": self.refit_count,
        }

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "SlidingWindowCalibrator":
        # Imported late to avoid a hard dependency at module import time;
        # the factory is resolved through the registry by name.
        from hugrgate.calibration import CalibratorRegistry
        factory_cls = CalibratorRegistry.get(params["factory_calibrator"])
        obj = cls(factory_cls,
                  window_size=int(params["window_size"]),
                  refit_every=int(params.get("refit_every", 50)),
                  min_samples=int(params.get("min_samples", 20)))
        obj._window.extend((float(s), int(y)) for s, y in params["window"])
        obj._inner = factory_cls.from_params(params["inner_params"])
        obj.refit_count = int(params.get("refit_count", 0))
        obj._fitted = True
        return obj
