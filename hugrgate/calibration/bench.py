"""Calibration benchmark suite. Slice 099.

Compares the calibration methods head-to-head on controlled synthetic
datasets with known miscalibration shapes.  Every dataset is generated from
a seeded PRNG, so the artifact is byte-identical on every run for a fixed
seed — no invented numbers, ever.

Datasets (``n`` samples each):
- ``overconfident`` — true ``p = σ(z)``, reported ``σ(2z)``;
- ``underconfident`` — true ``p = σ(z)``, reported ``σ(0.5z)``;
- ``label-noise`` — well-shaped scores, 15% flipped labels;
- ``well-calibrated`` — reported == true (control: calibration should be
  ~neutral here).

Entries: ``raw`` (identity baseline — the explicit baseline the slice
requires) plus every batch calibrator in the catalog.  Metrics: Brier,
log-loss, ECE, before → after.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence

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
from hugrgate.calibration.metrics import (
    brier_score,
    expected_calibration_error,
    log_loss,
)
from hugrgate.errors import CalibrationError

__all__ = [
    "DATASETS",
    "BENCH_CALIBRATORS",
    "generate_dataset",
    "run_benchmark",
]

DATASETS = ("overconfident", "underconfident", "label-noise",
            "well-calibrated")

BENCH_CALIBRATORS = ("raw", "platt", "isotonic", "temperature",
                      "beta-binomial", "ensemble")


class _RawBaseline(Calibrator):
    """Identity map: the explicit 'do nothing' baseline."""

    name = "raw"

    def fit(self, scores: Sequence[float],
            labels: Sequence[int]) -> "_RawBaseline":
        self._as_arrays(scores, labels)
        self._fitted = True
        return self

    def calibrate(self, score: float) -> float:
        self._check_fitted()
        return float(min(1.0, max(0.0, score)))

    def get_params(self) -> Dict[str, Any]:
        return {}

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "_RawBaseline":
        obj = cls()
        obj._fitted = True
        return obj


def generate_dataset(kind: str, n: int, seed: int
                     ) -> tuple[List[float], List[int]]:
    """Seeded synthetic (scores, labels) with a known miscalibration shape."""
    _require_numpy()
    if kind not in DATASETS:
        raise CalibrationError(f"unknown dataset {kind!r}")
    if n < 10:
        raise CalibrationError("n must be ≥ 10")
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.0, n)
    p_true = 1.0 / (1.0 + np.exp(-z))
    if kind == "overconfident":
        scores = 1.0 / (1.0 + np.exp(-2.0 * z))
    elif kind == "underconfident":
        scores = 1.0 / (1.0 + np.exp(-0.5 * z))
    else:
        scores = p_true.copy()
    labels = (rng.random(n) < p_true).astype(int)
    if kind == "label-noise":
        flips = rng.random(n) < 0.15
        labels = np.where(flips, 1 - labels, labels)
    return scores.tolist(), labels.tolist()


def _get(name: str) -> Callable[[], Calibrator]:
    if name == "raw":
        return _RawBaseline
    return CalibratorRegistry.get(name)


def run_benchmark(seed: int = 20261009, n: int = 2000,
                  datasets: Sequence[str] = DATASETS,
                  calibrators: Sequence[str] = BENCH_CALIBRATORS,
                  ) -> Dict[str, Any]:
    """Run the full benchmark; returns the artifact dict."""
    _require_numpy()
    results: List[Dict[str, Any]] = []
    for di, kind in enumerate(datasets):
        scores, labels = generate_dataset(kind, n, seed + di)
        raw_metrics = {
            "brier": brier_score(labels, scores),
            "log_loss": log_loss(labels, scores),
            "ece": expected_calibration_error(labels, scores),
        }
        for name in calibrators:
            cal = _get(name)()
            cal.fit(scores, labels)
            out = [cal.calibrate(float(v)) for v in scores]
            after = {
                "brier": brier_score(labels, out),
                "log_loss": log_loss(labels, out),
                "ece": expected_calibration_error(labels, out),
            }
            results.append({
                "dataset": kind,
                "calibrator": name,
                "n": n,
                "before": raw_metrics,
                "after": after,
                "delta_brier": raw_metrics["brier"] - after["brier"],
                "delta_ece": raw_metrics["ece"] - after["ece"],
            })
    return {
        "name": "calibration_500",
        "version": "1.0.0",
        "seed": seed,
        "n_per_dataset": n,
        "datasets": list(datasets),
        "calibrators": list(calibrators),
        "metric_note": ("before/after are in-sample on the benchmark fit "
                        "set; delta_* = before − after (positive is good)"),
        "results": results,
    }
