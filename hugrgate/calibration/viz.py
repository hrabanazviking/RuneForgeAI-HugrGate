"""Calibration visualization data. Slice 097.

Frontends need *data*, not plots: this module produces JSON-serializable
payloads for the standard calibration visuals, with no plotting dependency:

- :func:`reliability_curve_data` — reliability-diagram points
  (mean predicted vs. mean actual per bin) plus the ideal diagonal;
- :func:`confidence_histogram` — histogram of top-class confidences;
- :func:`per_class_ece_bars` — one-vs-rest ECE per class;
- :func:`risk_coverage_points` / :func:`selective_curve_points` —
  normalized pass-throughs of the slice-086/087 curves;
- :func:`calibration_dashboard` — the combined payload: summary metrics,
  reliability curve, histogram, per-class bars, and data-quality notes.

Every payload passes ``json.dumps`` — that invariant is tested.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

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
    maximum_calibration_error,
    reliability_diagram,
)
from hugrgate.errors import CalibrationError

__all__ = [
    "reliability_curve_data",
    "confidence_histogram",
    "per_class_ece_bars",
    "risk_coverage_points",
    "selective_curve_points",
    "calibration_dashboard",
]


def _jsonable(payload: Any) -> Any:
    # Fail fast if anything isn't JSON-serializable.
    json.dumps(payload)
    return payload


def reliability_curve_data(y_true: Sequence[int],
                           y_prob: Sequence[float],
                           n_bins: int = 10) -> Dict[str, Any]:
    """Reliability-diagram points + ideal diagonal + summary."""
    _require_numpy()
    bins = reliability_diagram(y_true, y_prob, n_bins)
    return _jsonable({
        "points": [
            {"bin_low": b["bin_low"], "bin_high": b["bin_high"],
             "mean_predicted": b["mean_predicted"],
             "mean_actual": b["mean_actual"],
             "gap": b["gap"], "count": b["count"]}
            for b in bins
        ],
        "diagonal": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}],
        "ece": expected_calibration_error(y_true, y_prob, n_bins),
        "mce": maximum_calibration_error(y_true, y_prob, n_bins),
        "n_bins": n_bins,
        "n_samples": len(list(y_true)),
    })


def confidence_histogram(probas: Sequence[Mapping[str, float]],
                         n_bins: int = 10) -> Dict[str, Any]:
    """Histogram of top-class confidences (detects over/under-confidence)."""
    _require_numpy()
    probas = list(probas)
    if not probas:
        raise CalibrationError("empty probas")
    conf = np.array([max(float(v) for v in d.values()) for d in probas])
    counts, edges = np.histogram(conf, bins=n_bins, range=(0.0, 1.0))
    return _jsonable({
        "bins": [{"low": float(edges[i]), "high": float(edges[i + 1]),
                  "count": int(counts[i]),
                  "fraction": float(counts[i]) / len(probas)}
                 for i in range(n_bins)],
        "mean_confidence": float(conf.mean()),
        "n_samples": len(probas),
    })


def per_class_ece_bars(y_true: Sequence[str],
                       probas: Sequence[Mapping[str, float]],
                       n_bins: int = 10) -> Dict[str, Any]:
    """One-vs-rest ECE per class for a bar chart."""
    _require_numpy()
    y_true = list(y_true)
    probas = list(probas)
    if len(y_true) != len(probas) or not y_true:
        raise CalibrationError("y_true/probas must be non-empty and aligned")
    classes = sorted({c for d in probas for c in d})
    bars = []
    for c in classes:
        yc = [1 if y == c else 0 for y in y_true]
        pc = [float(d.get(c, 0.0)) for d in probas]
        bars.append({"class": c,
                     "ece": expected_calibration_error(yc, pc, n_bins),
                     "brier": brier_score(yc, pc),
                     "support": float(sum(yc))})
    return _jsonable({"bars": bars, "n_classes": len(classes),
                      "n_samples": len(y_true)})


def risk_coverage_points(curve: Sequence[Dict[str, float]]) -> Dict[str, Any]:
    """Normalized pass-through of a slice-087 risk-coverage curve."""
    rows = [{"coverage": float(r["coverage"]), "risk": float(r["risk"]),
             "threshold": float(r.get("threshold", 0.0))}
            for r in curve]
    return _jsonable({"points": rows})


def selective_curve_points(curve: Sequence[Dict[str, float]]) -> Dict[str, Any]:
    """Normalized pass-through of a slice-086 selective-accuracy curve."""
    rows = [{"coverage": float(r["coverage"]),
             "accuracy": float(r["accuracy"]),
             "threshold": float(r.get("threshold", 0.0))}
            for r in curve]
    return _jsonable({"points": rows})


def calibration_dashboard(y_true: Sequence[str],
                          probas: Sequence[Mapping[str, float]],
                          n_bins: int = 10) -> Dict[str, Any]:
    """Combined dashboard payload for one multiclass evaluation."""
    _require_numpy()
    y_true = list(y_true)
    probas = list(probas)
    if len(y_true) != len(probas) or not y_true:
        raise CalibrationError("y_true/probas must be non-empty and aligned")
    classes = sorted({c for d in probas for c in d})
    # Binary view: top-class confidence vs. correctness.
    y_bin: List[int] = []
    p_bin: List[float] = []
    for y, d in zip(y_true, probas):
        top = max(d, key=lambda k: float(d[k]))
        y_bin.append(1 if top == y else 0)
        p_bin.append(float(d[top]))
    return _jsonable({
        "summary": {
            "n_samples": len(y_true),
            "n_classes": len(classes),
            "accuracy": float(sum(y_bin) / len(y_bin)),
            "mean_confidence": float(sum(p_bin) / len(p_bin)),
            "brier_top": brier_score(y_bin, p_bin),
            "ece_top": expected_calibration_error(y_bin, p_bin, n_bins),
            "mce_top": maximum_calibration_error(y_bin, p_bin, n_bins),
        },
        "reliability": reliability_curve_data(y_bin, p_bin, n_bins),
        "confidence_histogram": confidence_histogram(probas, n_bins),
        "per_class_ece": per_class_ece_bars(y_true, probas, n_bins),
    })
