"""Calibration under drift. Slice 088.

A calibration map is a bet that the future resembles the fit set.  When the
score→outcome relationship drifts, the bet goes bad silently — live ECE
climbs while nobody watches.  :class:`CalibrationDriftMonitor` watches the
*calibrated* outputs in production:

- each observed batch contributes Brier and ECE;
- the first ``baseline_batches`` batches establish the in-control mean and
  standard deviation of each metric;
- afterwards EWMAs of both metrics are compared against
  ``mean + k·std`` control limits (with a ``min_std`` floor so a
  suspiciously quiet baseline can't arm a hair-trigger) — crossing either
  limit raises an alarm and the monitor recommends ``"recalibrate"``.

Pair it with :class:`~hugrgate.calibration.online.OnlineCalibrator` or
:class:`~hugrgate.calibration.window.SlidingWindowCalibrator`: the monitor
says *when*, the adaptive calibrator does the *what*.  After recalibrating,
call :meth:`reset_alarm` to re-arm.
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

from hugrgate.calibration.metrics import (
    brier_score,
    expected_calibration_error,
)
from hugrgate.errors import CalibrationError

__all__ = [
    "CalibrationDriftMonitor",
    "DriftReport",
]


class DriftReport:
    """Point-in-time view of the monitor (JSON-serializable)."""

    def __init__(self, monitor: CalibrationDriftMonitor):
        self._m = monitor

    def as_dict(self) -> dict[str, Any]:
        m = self._m
        return {
            "batches_seen": m.batches_seen,
            "alarmed": m.alarmed,
            "alarm_batch": m.alarm_batch,
            "alarm_metric": m.alarm_metric,
            "baseline": m.baseline_stats(),
            "recommendation": m.recommend(),
            "history": [dict(h) for h in m.history],
        }


class CalibrationDriftMonitor:
    """EWMA control-chart monitor over batch Brier/ECE of calibrated outputs."""

    def __init__(self, baseline_batches: int = 5, k: float = 3.0,
                 ewma_alpha: float = 0.3, min_std: float = 1e-3,
                 n_bins: int = 10):
        if baseline_batches < 2:
            raise CalibrationError("baseline_batches must be ≥ 2")
        if k <= 0:
            raise CalibrationError("k must be positive")
        if not 0.0 < ewma_alpha <= 1.0:
            raise CalibrationError("ewma_alpha must be in (0, 1]")
        if min_std < 0:
            raise CalibrationError("min_std must be ≥ 0")
        self.baseline_batches = int(baseline_batches)
        self.k = float(k)
        self.ewma_alpha = float(ewma_alpha)
        self.min_std = float(min_std)
        self.n_bins = int(n_bins)
        self._history: list[dict[str, float]] = []
        self._ewma: dict[str, float] = {}
        self._alarmed = False
        self._alarm_batch: int | None = None
        self._alarm_metric: str | None = None

    @property
    def batches_seen(self) -> int:
        return len(self._history)

    @property
    def history(self) -> list[dict[str, float]]:
        return [dict(h) for h in self._history]

    @property
    def alarmed(self) -> bool:
        return self._alarmed

    @property
    def alarm_batch(self) -> int | None:
        return self._alarm_batch

    @property
    def alarm_metric(self) -> str | None:
        return self._alarm_metric

    def baseline_stats(self) -> dict[str, float]:
        _require_numpy()
        if self.batches_seen < self.baseline_batches:
            raise CalibrationError("baseline not yet established")
        base = self._history[: self.baseline_batches]
        out = {}
        for metric in ("brier", "ece"):
            vals = np.array([h[metric] for h in base])
            out[f"mean_{metric}"] = float(vals.mean())
            out[f"std_{metric}"] = float(
                max(vals.std(ddof=1), self.min_std))
        return out

    def control_limits(self) -> dict[str, float]:
        stats = self.baseline_stats()
        return {m: stats[f"mean_{m}"] + self.k * stats[f"std_{m}"]
                for m in ("brier", "ece")}

    def observe(self, scores: Sequence[float],
                labels: Sequence[int]) -> dict[str, float]:
        """Record one batch of calibrated outputs; update the alarm state."""
        _require_numpy()
        scores = list(scores)
        labels = list(labels)
        if not scores:
            raise CalibrationError("cannot observe an empty batch")
        if len(scores) != len(labels):
            raise CalibrationError("scores/labels length mismatch")
        metrics = {
            "brier": brier_score(labels, scores),
            "ece": expected_calibration_error(labels, scores, self.n_bins),
        }
        row: dict[str, float] = {
            "batch": float(self.batches_seen),
            "n": float(len(scores)),
            **metrics,
        }
        for m, v in metrics.items():
            self._ewma[m] = (v if m not in self._ewma
                             else self.ewma_alpha * v
                             + (1.0 - self.ewma_alpha) * self._ewma[m])
            row[f"ewma_{m}"] = self._ewma[m]
        self._history.append(row)
        if self.batches_seen > self.baseline_batches and not self._alarmed:
            limits = self.control_limits()
            for m in ("brier", "ece"):
                if self._ewma[m] > limits[m]:
                    self._alarmed = True
                    self._alarm_batch = self.batches_seen - 1
                    self._alarm_metric = m
                    break
        row["alarmed"] = 1.0 if self._alarmed else 0.0
        return dict(row)

    def recommend(self) -> str:
        """``"recalibrate"`` once alarmed, else ``"keep"``."""
        return "recalibrate" if self._alarmed else "keep"

    def reset_alarm(self) -> None:
        """Acknowledge the alarm after recalibration (history is kept)."""
        self._alarmed = False
        self._alarm_batch = None
        self._alarm_metric = None
        self._ewma = {}

    def report(self) -> DriftReport:
        return DriftReport(self)
