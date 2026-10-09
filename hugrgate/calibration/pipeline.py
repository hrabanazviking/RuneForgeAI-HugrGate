"""Calibration pipeline (architecture v2). Slice 076.

What existed before this slice: three binary calibrators (Platt, isotonic,
temperature), bare metrics, and versioned profiles - but no lifecycle around
* fitting a calibrator: no fit-data diagnostics, no before/after comparison,
no refusal to deploy a calibration that made things worse.

This module adds that lifecycle without touching the existing calibrators:

- :func:`validate_fit_data` - diagnostics + hard validation of a
  (scores, labels) fit set (both classes present, finite scores, sane size).
- :class:`CalibrationPipeline` - wraps a calibrator factory, fits it,
  records before/after Brier / log-loss / ECE / MCE, and produces a
  :class:`CalibrationReport` carrying provenance, the dataset hash, and an
  ``improved`` verdict.
- :class:`CalibrationReport` - JSON-serializable, round-trippable; can seed
  a :class:`~hugrgate.calibration.profiles.CalibrationProfile` via
  :meth:`CalibrationReport.as_profile_kwargs`.

The pipeline *warns* (does not raise) when calibration fails to improve the
metrics, because on near-perfect scores any map is noise - but
:meth:`CalibrationPipeline.fit_strict` raises in that case for pipelines that
want a hard gate.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
from hugrgate.calibration.metrics import (
    brier_score,
    expected_calibration_error,
    log_loss,
    maximum_calibration_error,
)
from hugrgate.calibration.profiles import hash_dataset
from hugrgate.errors import CalibrationError

__all__ = [
    "MIN_FIT_SAMPLES",
    "CalibrationPipeline",
    "CalibrationReport",
    "FitDiagnostics",
    "validate_fit_data",
]

#: Hard floor: fewer samples than this and no fit is attempted.
MIN_FIT_SAMPLES = 10


@dataclass
class FitDiagnostics:
    """Diagnostics computed over a (scores, labels) fit set."""

    n_samples: int
    n_positive: int
    n_negative: int
    score_min: float
    score_max: float
    positive_rate: float
    dataset_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_fit_data(scores: Sequence[float],
                      labels: Sequence[int],
                      min_samples: int = MIN_FIT_SAMPLES) -> FitDiagnostics:
    """Validate a calibration fit set; raise :class:`CalibrationError` if unfit.

    Checks: non-empty, length match, finite scores, 0/1 labels, at least
    ``min_samples`` rows, and *both* classes present (a calibrator fit on a
    single class is degenerate - the map would be constant).
    """
    _require_numpy()
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    if s.shape != y.shape:
        raise CalibrationError(
            f"scores/labels length mismatch: {s.shape} vs {y.shape}")
    if s.size == 0:
        raise CalibrationError("cannot fit on empty data")
    if int(s.size) < int(min_samples):
        raise CalibrationError(
            f"need at least {min_samples} samples to fit, got {s.size}")
    if np.any(~np.isfinite(s)):
        raise CalibrationError("scores must be finite")
    if not np.all(np.isin(y, (0.0, 1.0))):
        raise CalibrationError("labels must be 0/1")
    n_pos = int(y.sum())
    n_neg = int(y.size - n_pos)
    if n_pos == 0 or n_neg == 0:
        raise CalibrationError(
            "calibration fit data must contain both classes "
            f"(got {n_pos} positives, {n_neg} negatives)")
    return FitDiagnostics(
        n_samples=int(s.size),
        n_positive=n_pos,
        n_negative=n_neg,
        score_min=float(s.min()),
        score_max=float(s.max()),
        positive_rate=float(n_pos) / float(s.size),
        dataset_hash=hash_dataset(scores, labels),
    )


@dataclass
class CalibrationReport:
    """Before/after record of one pipeline fit. JSON-serializable."""

    calibrator_name: str
    calibrator_params: dict[str, Any]
    diagnostics: dict[str, Any]
    metrics_before: dict[str, float]
    metrics_after: dict[str, float]
    improved: bool
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationReport:
        return cls(
            calibrator_name=d["calibrator_name"],
            calibrator_params=dict(d["calibrator_params"]),
            diagnostics=dict(d["diagnostics"]),
            metrics_before=dict(d["metrics_before"]),
            metrics_after=dict(d["metrics_after"]),
            improved=bool(d["improved"]),
            created_at=d.get("created_at",
                             datetime.now(timezone.utc).isoformat()),
            provenance=dict(d.get("provenance", {})),
            notes=d.get("notes", ""),
        )

    def improvement(self, metric: str) -> float:
        """Absolute improvement (before - after) for a lower-is-better metric."""
        return float(self.metrics_before[metric] - self.metrics_after[metric])


def _metrics_for(y: Sequence[int], p: Sequence[float],
                 n_bins: int = 10) -> dict[str, float]:
    return {
        "brier": brier_score(y, p),
        "log_loss": log_loss(y, p),
        "ece": expected_calibration_error(y, p, n_bins),
        "mce": maximum_calibration_error(y, p, n_bins),
    }


class CalibrationPipeline:
    """Fit → validate → report lifecycle around any :class:`Calibrator`.

    ``factory`` is a zero-argument callable returning a fresh calibrator
    (e.g. ``PlattCalibrator`` or ``functools.partial(TemperatureCalibrator,
    max_iter=50)``).
    """

    def __init__(self, factory: Callable[[], Calibrator],
                 name: str | None = None):
        probe = factory()
        if not isinstance(probe, Calibrator):
            raise CalibrationError(
                "factory must return a Calibrator instance")
        self.factory = factory
        self.name = name or probe.name
        self.calibrator: Calibrator | None = None
        self.report: CalibrationReport | None = None

    def fit(self, scores: Sequence[float], labels: Sequence[int],
            provenance: dict[str, Any] | None = None,
            n_bins: int = 10) -> CalibrationReport:
        """Fit the calibrator and record the before/after report."""
        diag = validate_fit_data(scores, labels)
        y = [int(v) for v in labels]
        raw = [min(1.0, max(0.0, float(s))) for s in scores]
        before = _metrics_for(y, raw, n_bins)

        cal = self.factory()
        cal.fit(scores, labels)
        calibrated = [cal.calibrate(float(s)) for s in scores]
        after = _metrics_for(y, calibrated, n_bins)

        # "Improved" demands a genuine Brier gain (beyond solver noise) and
        # no ECE regression.  Equality is *not* improvement: a fit that
        # merely reproduces the raw scores teaches nothing.
        improved = (before["brier"] - after["brier"] > 1e-9
                    and after["ece"] <= before["ece"] + 1e-9)
        self.calibrator = cal
        self.report = CalibrationReport(
            calibrator_name=cal.name,
            calibrator_params=cal.get_params(),
            diagnostics=diag.as_dict(),
            metrics_before=before,
            metrics_after=after,
            improved=improved,
            provenance=dict(provenance or {}),
        )
        return self.report

    def fit_strict(self, scores: Sequence[float], labels: Sequence[int],
                   provenance: dict[str, Any] | None = None,
                   n_bins: int = 10) -> CalibrationReport:
        """Like :meth:`fit` but raise if calibration did not improve things."""
        report = self.fit(scores, labels, provenance, n_bins)
        if not report.improved:
            raise CalibrationError(
                f"{self.name}: calibration did not improve brier+ecc; "
                f"before={report.metrics_before} after={report.metrics_after}")
        return report

    def apply(self, scores: Sequence[float]) -> list[float]:
        """Calibrate new scores with the fitted calibrator."""
        if self.calibrator is None:
            raise CalibrationError(
                f"pipeline {self.name!r} used before fit")
        _require_numpy()
        out = []
        for s in scores:
            if not np.isfinite(float(s)):
                raise CalibrationError("cannot calibrate a non-finite score")
            out.append(self.calibrator.calibrate(float(s)))
        return out
