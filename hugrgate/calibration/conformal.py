"""Split-conformal classification. Slice 082.

Where calibration asks "is 0.8 really 80%?", conformal prediction asks "which
set of labels covers the truth with probability ≥ 1−α?"  :class:`ConformalClassifier`
implements split (inductive) conformal prediction for classifiers:

- nonconformity score ``s(x, y) = 1 − p̂(y | x)`` on a held-out calibration
  fold;
- threshold ``q̂`` = the ``⌈(n+1)(1−α)⌉/n`` quantile of those scores;
- prediction set ``{c : p̂(c | x) ≥ 1 − q̂}``.

Under exchangeability of calibration and test data, the set covers the true
label with probability at least ``1 − α`` (finite-sample guarantee).  An
optional Mondrian (group-conditional) mode fits one threshold per group for
group-conditional coverage.

This module returns plain ``frozenset`` prediction sets; slice 084's
:class:`~hugrgate.calibration.sets.PredictionSet` adds the set-metric
abstraction on top.
"""

from __future__ import annotations

import math
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence

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
    "ConformalClassifier",
]


def _quantile(scores: np.ndarray, alpha: float) -> float:
    """⌈(n+1)(1−α)⌉/n quantile (the conformal finite-sample correction)."""
    n = scores.size
    k = int(math.ceil((n + 1) * (1.0 - alpha)))
    k = min(n, max(1, k))
    return float(np.sort(scores)[k - 1])


class ConformalClassifier:
    """Split-conformal prediction sets for multiclass classifiers."""

    def __init__(self, alpha: float = 0.1):
        if not 0.0 < alpha < 1.0:
            raise CalibrationError("alpha must be in (0, 1)")
        self.alpha = float(alpha)
        self._thresholds: Dict[str, float] = {}
        self._classes: List[str] = []
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    def fit(self, probas: Sequence[Mapping[str, float]],
            labels: Sequence[str],
            groups: Optional[Sequence[str]] = None) -> "ConformalClassifier":
        """Fit thresholds on a held-out calibration fold.

        ``groups`` enables Mondrian (group-conditional) conformal: one
        threshold per group value.
        """
        _require_numpy()
        probas = list(probas)
        labels = list(labels)
        if len(probas) != len(labels):
            raise CalibrationError("probas/labels length mismatch")
        if not probas:
            raise CalibrationError("cannot fit on empty data")
        self._classes = sorted({c for d in probas for c in d} | set(labels))
        group_ids = (["__global__"] * len(probas) if groups is None
                     else [str(g) for g in groups])
        if len(group_ids) != len(probas):
            raise CalibrationError("groups length mismatch")

        by_group: Dict[str, List[float]] = {}
        for d, y, g in zip(probas, labels, group_ids):
            if y not in d:
                raise CalibrationError(
                    f"true label {y!r} missing from a proba dict")
            by_group.setdefault(g, []).append(1.0 - float(d[y]))
        self._thresholds = {
            g: _quantile(np.asarray(s), self.alpha)
            for g, s in by_group.items()
        }
        self._fitted = True
        return self

    def _threshold_for(self, group: Optional[str]) -> float:
        if not self._fitted:
            raise CalibrationError("ConformalClassifier used before fit")
        key = "__global__" if group is None else str(group)
        try:
            return self._thresholds[key]
        except KeyError:
            raise CalibrationError(
                f"no conformal threshold for group {group!r}; "
                f"known: {sorted(self._thresholds)}")

    def predict_set(self, proba: Mapping[str, float],
                    group: Optional[str] = None) -> FrozenSet[str]:
        """Prediction set with marginal (or group-conditional) 1−α coverage."""
        q = self._threshold_for(group)
        cutoff = 1.0 - q
        chosen = {c for c, p in proba.items() if float(p) >= cutoff}
        if not chosen:
            # Never return an empty set: fall back to the argmax.
            top = max(proba, key=lambda c: float(proba[c]))
            chosen = {top}
        return frozenset(chosen)

    def predict_sets(self, probas: Sequence[Mapping[str, float]],
                     groups: Optional[Sequence[str]] = None
                     ) -> List[FrozenSet[str]]:
        probas = list(probas)
        group_list = ([None] * len(probas) if groups is None
                      else list(groups))
        if len(group_list) != len(probas):
            raise CalibrationError("groups length mismatch")
        return [self.predict_set(d, g)
                for d, g in zip(probas, group_list)]

    def empirical_coverage(self, probas: Sequence[Mapping[str, float]],
                           labels: Sequence[str],
                           groups: Optional[Sequence[str]] = None) -> float:
        """Fraction of prediction sets containing the true label."""
        sets = self.predict_sets(probas, groups)
        labels = list(labels)
        if len(sets) != len(labels):
            raise CalibrationError("probas/labels length mismatch")
        hits = sum(1 for s, y in zip(sets, labels) if y in s)
        return hits / len(sets) if sets else 0.0

    def mean_set_size(self, probas: Sequence[Mapping[str, float]],
                      groups: Optional[Sequence[str]] = None) -> float:
        sets = self.predict_sets(probas, groups)
        return sum(len(s) for s in sets) / len(sets) if sets else 0.0

    @property
    def thresholds(self) -> Dict[str, float]:
        return dict(self._thresholds)
