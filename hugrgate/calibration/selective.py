"""Selective prediction curves. Slice 086.

Selective prediction: answer only when confident, abstain otherwise.  Given
per-decision confidences and correctness flags, this module builds the
*selective accuracy curve* — accuracy as a function of the fraction of
decisions kept (coverage) — plus the area under it and coverage lookup at a
target accuracy.

Slice 087's risk-coverage curves are the loss-based sibling; this module is
the accuracy-based one.  Both consume the same ``(confidence, correct)``
pairs, so either can be derived from HugrGate decision logs.
"""

from __future__ import annotations

from collections.abc import Sequence

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
    "accuracy_at_coverage",
    "area_under_selective_curve",
    "coverage_at_accuracy",
    "selective_curve",
]


def _check(confidences: Sequence[float],
           correct: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    _require_numpy()
    c = np.asarray(list(confidences), dtype=float)
    y = np.asarray(list(correct), dtype=float)
    if c.shape != y.shape:
        raise CalibrationError("confidences/correct length mismatch")
    if c.size == 0:
        raise CalibrationError("empty inputs")
    if np.any(~np.isfinite(c)):
        raise CalibrationError("confidences must be finite")
    if np.any((c < 0.0) | (c > 1.0)):
        raise CalibrationError("confidences must be in [0, 1]")
    if not np.all(np.isin(y, (0.0, 1.0))):
        raise CalibrationError("correct must be 0/1")
    return c, y


def selective_curve(confidences: Sequence[float],
                     correct: Sequence[int],
                     n_points: int = 50) -> list[dict[str, float]]:
    """Selective accuracy curve over ``n_points`` coverage levels.

    Each row: ``{threshold, coverage, accuracy, n}`` — the accuracy among
    decisions with ``confidence ≥ threshold``.  Rows run from full coverage
    (threshold 0) down to the most confident sliver.
    """
    c, y = _check(confidences, correct)
    if n_points < 2:
        raise CalibrationError("n_points must be ≥ 2")
    order = np.argsort(-c, kind="stable")
    cs, ys = c[order], y[order]
    n = c.size
    rows: list[dict[str, float]] = []
    for i in range(n_points):
        # Keep the top (i+1)/n_points fraction, at least one decision.
        k = max(1, round(n * (i + 1) / n_points))
        kept_c, kept_y = cs[:k], ys[:k]
        rows.append({
            "threshold": float(kept_c[-1]),
            "coverage": float(k) / float(n),
            "accuracy": float(kept_y.mean()),
            "n": float(k),
        })
    return rows


def area_under_selective_curve(curve: Sequence[dict[str, float]]) -> float:
    """Normalized area under the selective accuracy curve (trapezoid)."""
    rows = list(curve)
    if len(rows) < 2:
        raise CalibrationError("need at least 2 curve points")
    _require_numpy()
    order = np.argsort([r["coverage"] for r in rows])
    xs = np.array([rows[i]["coverage"] for i in order])
    ys = np.array([rows[i]["accuracy"] for i in order])
    # Anchor at coverage 0 with the most-selective accuracy: the curve is
    # defined (in the limit) down to the single most confident decision.
    if xs[0] > 0.0:
        xs = np.concatenate([[0.0], xs])
        ys = np.concatenate([[ys[0]], ys])
    return float(np.trapezoid(ys, xs))


def accuracy_at_coverage(curve: Sequence[dict[str, float]],
                         coverage: float) -> float:
    """Interpolated selective accuracy at a target coverage."""
    if not 0.0 < coverage <= 1.0:
        raise CalibrationError("coverage must be in (0, 1]")
    rows = sorted(curve, key=lambda r: r["coverage"])
    xs = [r["coverage"] for r in rows]
    ys = [r["accuracy"] for r in rows]
    return float(np.interp(coverage, xs, ys))


def coverage_at_accuracy(curve: Sequence[dict[str, float]],
                         accuracy: float) -> float:
    """Largest coverage whose interpolated accuracy stays ≥ ``accuracy``."""
    if not 0.0 <= accuracy <= 1.0:
        raise CalibrationError("accuracy must be in [0, 1]")
    best = 0.0
    for r in curve:
        if r["accuracy"] >= accuracy:
            best = max(best, float(r["coverage"]))
    return float(best)
