"""Calibration auto-selection. Slice 092.

Instead of tribal knowledge ("always use isotonic"), pick the calibrator by
seeded K-fold cross-validation on the actual fit data.  :func:`auto_select`
evaluates candidate calibrators from the slice-091 catalog on a proper
scoring rule (Brier, log-loss) or ECE, ranks them by held-out mean, and
returns the winner *refit on the full data*.

Candidate defaults: the non-streaming, non-fallback, non-deprecated catalog
entries (platt, isotonic, temperature, beta-binomial).  Streaming calibrators
are excluded by default because fold semantics differ for them — pass them
explicitly if you want them compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

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
from hugrgate.calibration.registry import find
from hugrgate.errors import CalibrationError

__all__ = [
    "DEFAULT_CANDIDATES",
    "SelectionResult",
    "auto_select",
]

_METRICS: Dict[str, Callable[[Sequence[int], Sequence[float]], float]] = {
    "brier": brier_score,
    "log_loss": log_loss,
    "ece": expected_calibration_error,
}

DEFAULT_CANDIDATES: List[str] = [
    s.name for s in find()
    if s.family in ("parametric", "nonparametric", "bayesian")
]


@dataclass
class SelectionResult:
    """Outcome of :func:`auto_select` (JSON-serializable summary)."""

    metric: str
    n_folds: int
    seed: int
    ranking: List[Dict[str, Any]]  # {name, mean, std, folds}, best first
    best: str
    best_params: Dict[str, Any]
    n_samples: int
    notes: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "n_folds": self.n_folds,
            "seed": self.seed,
            "ranking": [dict(r) for r in self.ranking],
            "best": self.best,
            "best_params": dict(self.best_params),
            "n_samples": self.n_samples,
            "notes": self.notes,
        }


def _folds(n: int, n_folds: int, seed: int) -> List[np.ndarray]:
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    return [idx[i::n_folds] for i in range(n_folds)]


def auto_select(scores: Sequence[float], labels: Sequence[int],
                candidates: Optional[Sequence[str]] = None,
                metric: str = "brier",
                n_folds: int = 5, seed: int = 0,
                refit_best: bool = True) -> SelectionResult:
    """Cross-validate candidate calibrators; return the ranked result."""
    _require_numpy()
    if metric not in _METRICS:
        raise CalibrationError(
            f"unknown metric {metric!r}; choose from {sorted(_METRICS)}")
    if n_folds < 2:
        raise CalibrationError("n_folds must be ≥ 2")
    names: List[str] = (list(candidates) if candidates is not None
                        else list(DEFAULT_CANDIDATES))
    if not names:
        raise CalibrationError("no candidate calibrators")
    score_fn = _METRICS[metric]
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=int)
    if s.shape != y.shape or s.size == 0:
        raise CalibrationError("scores/labels must be non-empty and aligned")
    if n_folds > s.size:
        raise CalibrationError("n_folds exceeds sample count")

    ranking: List[Dict[str, Any]] = []
    for name in names:
        cls = CalibratorRegistry.get(name)  # raises on unknown names
        fold_scores = []
        for fold in _folds(s.size, n_folds, seed):
            train = np.ones(s.size, dtype=bool)
            train[fold] = False
            # Skip folds whose train split is single-class.
            if y[train].sum() in (0, train.sum()):
                continue
            cal: Calibrator = cls()
            try:
                cal.fit(s[train].tolist(), y[train].tolist())
            except CalibrationError:
                continue  # e.g. temperature on a degenerate split
            preds = [cal.calibrate(float(v)) for v in s[fold].tolist()]
            fold_scores.append(score_fn(y[fold].tolist(), preds))
        if not fold_scores:
            raise CalibrationError(
                f"candidate {name!r}: no usable CV folds")
        ranking.append({
            "name": name,
            "mean": float(np.mean(fold_scores)),
            "std": float(np.std(fold_scores, ddof=1)) if len(fold_scores) > 1 else 0.0,
            "folds": float(len(fold_scores)),
        })
    ranking.sort(key=lambda r: (r["mean"], r["name"]))
    best = ranking[0]["name"]
    best_params: Dict[str, Any] = {}
    if refit_best:
        winner = CalibratorRegistry.get(best)()
        winner.fit(s.tolist(), y.tolist())
        best_params = winner.get_params()
    return SelectionResult(
        metric=metric, n_folds=n_folds, seed=seed,
        ranking=ranking, best=best, best_params=best_params,
        n_samples=int(s.size),
        notes=f"lower {metric} is better; held-out means over CV folds",
    )
