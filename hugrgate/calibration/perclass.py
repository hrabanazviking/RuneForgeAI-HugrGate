"""Per-class calibration. Slice 077.

``CalibratedBackend`` already applied one-vs-rest calibrators per class, but
there was no principled *fitting* side: callers had to hand-roll the per-class
loop and hand-assemble ``CalibrationProfile.calibrator_params``.  This module
provides :class:`PerClassCalibrator`, which:

- fits one binary calibrator per class (one-vs-rest) from multiclass
  probability dicts + labels, via any :class:`Calibrator` factory;
- records per-class fit diagnostics (Brier/ECE before/after) so a single
  badly-calibrated class is visible instead of being averaged away;
- handles classes absent from the fit data with a constant-prior fallback
  instead of crashing (a class unseen during calibration still needs a
  prediction at serving time);
- renormalizes the calibrated distribution and exports/imports
  :class:`~hugrgate.calibration.profiles.CalibrationProfile` parameter dicts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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
)
from hugrgate.calibration.pipeline import validate_fit_data
from hugrgate.calibration.profiles import CalibrationProfile
from hugrgate.errors import CalibrationError

__all__ = [
    "PerClassCalibrator",
    "build_profile",
]


class _ConstantCalibrator(Calibrator):
    """Fallback: always emits a fixed probability (the class prior)."""

    name = "constant-prior"

    def __init__(self, prior: float = 0.5):
        super().__init__()
        if not 0.0 <= prior <= 1.0:
            raise CalibrationError("prior must be in [0, 1]")
        self.prior = float(prior)

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> _ConstantCalibrator:
        self._as_arrays(scores, labels)  # validate only
        self._fitted = True
        return self

    def calibrate(self, score: float) -> float:
        self._check_fitted()
        return self.prior

    def get_params(self) -> dict[str, Any]:
        self._check_fitted()
        return {"prior": self.prior}

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> _ConstantCalibrator:
        obj = cls(float(params["prior"]))
        obj._fitted = True
        return obj


class PerClassCalibrator:
    """One-vs-rest calibration for multiclass probability dicts.

    ``factory`` builds a fresh binary :class:`Calibrator` per class.
    """

    def __init__(self, factory: Callable[[], Calibrator]):
        probe = factory()
        if not isinstance(probe, Calibrator):
            raise CalibrationError("factory must return a Calibrator")
        self.factory = factory
        self.calibrator_name = probe.name
        self._units: dict[str, Calibrator] = {}
        self._classes: list[str] = []
        self._per_class_metrics: dict[str, dict[str, float]] = {}
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    @property
    def classes(self) -> list[str]:
        return list(self._classes)

    @property
    def per_class_metrics(self) -> dict[str, dict[str, float]]:
        return {k: dict(v) for k, v in self._per_class_metrics.items()}

    def fit(self, probas: Sequence[Mapping[str, float]],
            labels: Sequence[str],
            classes: Sequence[str] | None = None) -> PerClassCalibrator:
        """Fit one calibrator per class (one-vs-rest).

        ``classes`` optionally declares the full label set; classes absent
        from ``labels`` get the constant-prior fallback.
        """
        _require_numpy()
        probas = list(probas)
        labels = list(labels)
        if len(probas) != len(labels):
            raise CalibrationError(
                f"probas/labels length mismatch: {len(probas)} vs {len(labels)}")
        if not probas:
            raise CalibrationError("cannot fit on empty data")
        declared = list(classes) if classes is not None else sorted(
            {c for d in probas for c in d} | set(labels))
        if not declared:
            raise CalibrationError("no classes found in fit data")

        for cls_name in declared:
            scores = [float(d.get(cls_name, 0.0)) for d in probas]
            y = [1 if lab == cls_name else 0 for lab in labels]
            if sum(y) == 0 or sum(y) == len(y):
                # Class unseen (or universal) in the fit set: fall back to
                # the empirical prior instead of fitting a degenerate map.
                prior = sum(y) / len(y)
                unit: Calibrator = _ConstantCalibrator(prior)
                unit.fit(scores, y)
                before = after = {
                    "brier": brier_score(y, scores),
                    "ece": expected_calibration_error(y, scores),
                }
            else:
                validate_fit_data(scores, y, min_samples=2)
                unit = self.factory()
                unit.fit(scores, y)
                cal_scores = [unit.calibrate(s) for s in scores]
                before = {
                    "brier": brier_score(y, scores),
                    "ece": expected_calibration_error(y, scores),
                }
                after = {
                    "brier": brier_score(y, cal_scores),
                    "ece": expected_calibration_error(y, cal_scores),
                }
            self._units[cls_name] = unit
            self._per_class_metrics[cls_name] = {
                "brier_before": before["brier"],
                "brier_after": after["brier"],
                "ece_before": before["ece"],
                "ece_after": after["ece"],
                "n_positive": float(sum(y)),
                "fallback": 1.0 if isinstance(unit, _ConstantCalibrator) else 0.0,
            }
        self._classes = declared
        self._fitted = True
        return self

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise CalibrationError("PerClassCalibrator used before fit")

    def calibrate_dist(self, proba: Mapping[str, float]) -> dict[str, float]:
        """Calibrate one distribution; renormalize over declared classes."""
        self._check_fitted()
        out = {c: self._units[c].calibrate(float(proba.get(c, 0.0)))
               for c in self._classes}
        total = sum(out.values())
        if total <= 0:
            n = len(out)
            return {k: 1.0 / n for k in out}
        return {k: v / total for k, v in out.items()}

    def calibrate_batch(
            self, probas: Sequence[Mapping[str, float]]) -> list[dict[str, float]]:
        return [self.calibrate_dist(d) for d in probas]

    def to_profile_params(self) -> dict[str, dict[str, Any]]:
        """Export per-class params for ``CalibrationProfile``."""
        self._check_fitted()
        return {c: {"__fallback__": isinstance(u, _ConstantCalibrator),
                    **u.get_params()}
                for c, u in self._units.items()}

    @classmethod
    def from_profile_params(cls, factory: Callable[[], Calibrator],
                            params: dict[str, dict[str, Any]]
                            ) -> PerClassCalibrator:
        obj = cls(factory)
        for cls_name, p in params.items():
            p = dict(p)
            fallback = p.pop("__fallback__", False)
            unit: Calibrator = (_ConstantCalibrator.from_params(p) if fallback
                                else factory().from_params(p))
            obj._units[cls_name] = unit
        obj._classes = sorted(obj._units)
        obj._fitted = True
        return obj

def build_profile(name: str, per_class: PerClassCalibrator,
                  backend_name: str = "", model_name: str = "",
                  model_version: str = "",
                  version: str = "1.0.0") -> CalibrationProfile:
    """Build a :class:`CalibrationProfile` from a fitted PerClassCalibrator."""
    metrics: dict[str, float] = {}
    for cls_name, m in per_class.per_class_metrics.items():
        metrics[f"brier_before[{cls_name}]"] = m["brier_before"]
        metrics[f"brier_after[{cls_name}]"] = m["brier_after"]
        metrics[f"ece_after[{cls_name}]"] = m["ece_after"]
    return CalibrationProfile(
        name=name,
        version=version,
        backend_name=backend_name,
        model_name=model_name,
        model_version=model_version,
        calibrator_name=per_class.calibrator_name,
        calibrator_params=per_class.to_profile_params(),
        metrics=metrics,
    )
