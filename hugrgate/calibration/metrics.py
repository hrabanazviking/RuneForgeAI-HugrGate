"""Calibration metrics. Slice 28.

Binary metrics — Brier score, log loss, expected/maximum calibration error
(ECE/MCE) — plus reliability-diagram bin data and a multiclass ECE helper
(max-probability confidence vs. correctness) for whole-distribution checks.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]

from hugrgate.errors import CalibrationError


def _require_numpy() -> None:
    """Deliberate error when the optional numpy dependency is absent."""
    if np is None:  # pragma: no cover - optional dependency
        raise CalibrationError(
            "numpy is required for calibration; install the 'ml' extra: pip install 'hugrgate[ml]'"
        )

__all__ = [
    "brier_score",
    "log_loss",
    "reliability_diagram",
    "expected_calibration_error",
    "maximum_calibration_error",
    "ece_multiclass",
]

_EPS = 1e-15


def _check_binary(y_true: Sequence[int],
                  y_prob: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    _require_numpy()
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(y_prob), dtype=float)
    if y.shape != p.shape:
        raise ValueError(f"length mismatch: {y.shape} vs {p.shape}")
    if y.size == 0:
        raise ValueError("empty inputs")
    if not np.all(np.isin(y, (0.0, 1.0))):
        raise ValueError("y_true must be 0/1")
    if np.any((p < 0.0) | (p > 1.0)):
        raise ValueError("y_prob must be in [0, 1]")
    return y, p


def brier_score(y_true: Sequence[int], y_prob: Sequence[float]) -> float:
    """Mean squared error between predicted probabilities and 0/1 labels."""
    _require_numpy()
    y, p = _check_binary(y_true, y_prob)
    return float(np.mean((p - y) ** 2))


def log_loss(y_true: Sequence[int], y_prob: Sequence[float],
             eps: float = _EPS) -> float:
    """Binary cross-entropy (natural log)."""
    _require_numpy()
    y, p = _check_binary(y_true, y_prob)
    pc = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(pc) + (1.0 - y) * np.log(1.0 - pc)))


def reliability_diagram(y_true: Sequence[int], y_prob: Sequence[float],
                        n_bins: int = 10) -> List[Dict[str, float]]:
    """Per-bin ``{bin edges, count, mean predicted, mean actual, gap}`` data.

    Equal-width bins over [0, 1]; the last bin is closed on the right so a
    probability of exactly 1.0 lands somewhere.
    """
    _require_numpy()
    y, p = _check_binary(y_true, y_prob)
    if n_bins < 1:
        raise ValueError("n_bins must be ≥ 1")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: List[Dict[str, float]] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        count = int(mask.sum())
        if count:
            mean_pred = float(p[mask].mean())
            mean_true = float(y[mask].mean())
        else:
            mean_pred = (lo + hi) / 2.0
            mean_true = 0.0
        bins.append({
            "bin": float(i),
            "bin_low": lo,
            "bin_high": hi,
            "count": float(count),
            "fraction": float(count) / float(y.size),
            "mean_predicted": mean_pred,
            "mean_actual": mean_true,
            "gap": abs(mean_pred - mean_true),
        })
    return bins


def expected_calibration_error(y_true: Sequence[int],
                               y_prob: Sequence[float],
                               n_bins: int = 10) -> float:
    """ECE: Σ_b (n_b / N) · |acc_b − conf_b|."""
    bins = reliability_diagram(y_true, y_prob, n_bins)
    return float(sum(b["fraction"] * b["gap"] for b in bins))


def maximum_calibration_error(y_true: Sequence[int],
                              y_prob: Sequence[float],
                              n_bins: int = 10) -> float:
    """MCE: max_b |acc_b − conf_b| over non-empty bins."""
    bins = reliability_diagram(y_true, y_prob, n_bins)
    nonempty = [b["gap"] for b in bins if b["count"] > 0]
    return float(max(nonempty)) if nonempty else 0.0


def ece_multiclass(y_true: Sequence[str],
                   probas: Sequence[Dict[str, float]],
                   n_bins: int = 10) -> float:
    """Multiclass ECE: confidence = max probability, correct = argmax hit.

    Each prediction contributes its top-class probability as the confidence
    and whether the top class was right as the 0/1 outcome.
    """
    y_true = list(y_true)
    probas = list(probas)
    if len(y_true) != len(probas):
        raise ValueError("length mismatch")
    if not y_true:
        raise ValueError("empty inputs")
    confidences: List[float] = []
    correct: List[int] = []
    for true_label, dist in zip(y_true, probas):
        if not dist:
            raise ValueError("empty distribution")
        top = max(dist, key=lambda k: dist[k])
        confidences.append(float(dist[top]))
        correct.append(1 if top == true_label else 0)
    return expected_calibration_error(correct, confidences, n_bins)
