"""Prediction sets. Slice 084.

Slice 082 produced raw ``frozenset`` prediction sets with a coverage
guarantee.  This module adds the *abstraction* on top:

- :class:`PredictionSet` — an immutable set with its construction method,
  parameters, and provenance attached, so a set can be audited later;
- construction strategies: fixed ``threshold``, ``top_k``, cumulative-mass
  (APS-lite), and wrapping a fitted
  :class:`~hugrgate.calibration.conformal.ConformalClassifier`;
- set metrics: coverage, mean size, and *size-stratified* coverage, which
  catches the classic failure where large sets cover fine but singletons
  (the "confident" predictions) systematically miss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set

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
    "PredictionSet",
    "threshold_set",
    "topk_set",
    "cumulative_set",
    "set_metrics",
    "size_stratified_coverage",
]


@dataclass(frozen=True)
class PredictionSet:
    """An immutable prediction set with audit metadata."""

    labels: FrozenSet[str]
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.labels:
            raise CalibrationError("prediction set must not be empty")
        object.__setattr__(self, "labels", frozenset(self.labels))

    @property
    def size(self) -> int:
        return len(self.labels)

    def covers(self, label: str) -> bool:
        return label in self.labels

    def as_dict(self) -> Dict[str, Any]:
        return {
            "labels": sorted(self.labels),
            "method": self.method,
            "params": dict(self.params),
            "provenance": dict(self.provenance),
        }


def _check_proba(proba: Mapping[str, float]) -> Dict[str, float]:
    _require_numpy()
    d = {str(k): float(v) for k, v in proba.items()}
    if not d:
        raise CalibrationError("empty probability dict")
    if any(not np.isfinite(v) for v in d.values()):
        raise CalibrationError("probabilities must be finite")
    if any(v < 0.0 for v in d.values()):
        raise CalibrationError("probabilities must be non-negative")
    return d


def threshold_set(proba: Mapping[str, float],
                  threshold: float) -> PredictionSet:
    """All labels with ``p ≥ threshold`` (argmax fallback if empty)."""
    d = _check_proba(proba)
    if not 0.0 < threshold <= 1.0:
        raise CalibrationError("threshold must be in (0, 1]")
    chosen = {c for c, p in d.items() if p >= threshold}
    if not chosen:
        chosen = {max(d, key=lambda c: d[c])}
    return PredictionSet(frozenset(chosen), "threshold",
                         {"threshold": threshold})


def topk_set(proba: Mapping[str, float], k: int) -> PredictionSet:
    """The ``k`` most probable labels."""
    d = _check_proba(proba)
    if k < 1:
        raise CalibrationError("k must be ≥ 1")
    ranked = sorted(d, key=lambda c: d[c], reverse=True)
    return PredictionSet(frozenset(ranked[: min(k, len(ranked))]), "top-k",
                         {"k": k})


def cumulative_set(proba: Mapping[str, float],
                   mass: float) -> PredictionSet:
    """Smallest set of top labels whose probabilities sum to ≥ ``mass``."""
    d = _check_proba(proba)
    if not 0.0 < mass <= 1.0:
        raise CalibrationError("mass must be in (0, 1]")
    ranked = sorted(d, key=lambda c: d[c], reverse=True)
    chosen: Set[str] = set()
    total = 0.0
    for c in ranked:
        chosen.add(c)
        total += d[c]
        if total >= mass:
            break
    return PredictionSet(frozenset(chosen), "cumulative",
                         {"mass": mass, "covered_mass": total})


def from_conformal(proba: Mapping[str, float],
                   conformal: Any,
                   group: Optional[str] = None) -> PredictionSet:
    """Wrap a fitted ``ConformalClassifier.predict_set`` result."""
    raw = conformal.predict_set(dict(proba), group=group)
    return PredictionSet(
        frozenset(raw), "conformal",
        {"alpha": conformal.alpha,
         "threshold": conformal.thresholds.get(
             "__global__" if group is None else str(group))},
        {"group": group})


def set_metrics(sets: Sequence[PredictionSet],
                labels: Sequence[str]) -> Dict[str, float]:
    """Coverage, mean/median/max size over a batch of prediction sets."""
    _require_numpy()
    sets = list(sets)
    labels = list(labels)
    if len(sets) != len(labels):
        raise CalibrationError("sets/labels length mismatch")
    if not sets:
        raise CalibrationError("empty set batch")
    sizes = np.asarray([s.size for s in sets], dtype=float)
    hits = sum(1 for s, y in zip(sets, labels) if s.covers(y))
    return {
        "coverage": hits / len(sets),
        "mean_size": float(sizes.mean()),
        "median_size": float(np.median(sizes)),
        "max_size": float(sizes.max()),
        "singleton_rate": float((sizes == 1).mean()),
        "n": float(len(sets)),
    }


def size_stratified_coverage(sets: Sequence[PredictionSet],
                             labels: Sequence[str]
                             ) -> List[Dict[str, float]]:
    """Coverage broken down by prediction-set size.

    A healthy system covers ~equally at every size; if singletons cover
    much worse than large sets, the underlying scores are overconfident.
    """
    sets = list(sets)
    labels = list(labels)
    if len(sets) != len(labels):
        raise CalibrationError("sets/labels length mismatch")
    by_size: Dict[int, List[int]] = {}
    for s, y in zip(sets, labels):
        by_size.setdefault(s.size, []).append(1 if s.covers(y) else 0)
    rows = []
    for size in sorted(by_size):
        hits = by_size[size]
        rows.append({
            "size": float(size),
            "n": float(len(hits)),
            "coverage": sum(hits) / len(hits),
        })
    return rows
