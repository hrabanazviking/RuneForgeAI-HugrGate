"""Calibration auto-selection. Slice 092, hardened in slice 461.

Instead of tribal knowledge ("always use isotonic"), pick the calibrator by
seeded K-fold cross-validation on the actual fit data.  :func:`auto_select`
evaluates candidate calibrators from the slice-091 catalog on a proper
scoring rule (Brier, log-loss) or ECE, ranks them by held-out mean, and
returns the winner *refit on the full data*.

Slice 461 hardening (backward compatible — defaults preserve slice-092
behavior):

- ``"none"`` pseudo-candidate: the identity calibrator (raw scores).
  Selection can now conclude that *no* calibration beats the raw
  scores, which the old code could never express.
- ``incumbent`` + ``min_win``: when an incumbent calibrator is named,
  a challenger wins only if its *paired* fold-by-fold win over the
  incumbent clears ``min_win`` (mean of per-fold differences minus one
  standard error). Otherwise the incumbent is kept — "do no harm"
  beats chasing noise.
- Fold scores are tracked per fold index so the paired comparison is
  aligned even when candidates skip different degenerate folds.

Candidate defaults: the non-streaming, non-fallback, non-deprecated catalog
entries (platt, isotonic, temperature, beta-binomial).  Streaming calibrators
are excluded by default because fold semantics differ for them — pass them
explicitly if you want them compared.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
    "NONE_CANDIDATE",
    "SelectionResult",
    "auto_select",
    "paired_win",
]

#: Pseudo-candidate name for the identity calibrator (raw scores).
NONE_CANDIDATE = "none"

_METRICS: dict[str, Callable[[Sequence[int], Sequence[float]], float]] = {
    "brier": brier_score,
    "log_loss": log_loss,
    "ece": expected_calibration_error,
}

DEFAULT_CANDIDATES: list[str] = [
    s.name for s in find()
    if s.family in ("parametric", "nonparametric", "bayesian")
]


@dataclass
class SelectionResult:
    """Outcome of :func:`auto_select` (JSON-serializable summary)."""

    metric: str
    n_folds: int
    seed: int
    ranking: list[dict[str, Any]]  # {name, mean, std, folds}, best first
    best: str
    best_params: dict[str, Any]
    n_samples: int
    notes: str = ""
    # Slice 461: incumbent protection.
    incumbent: str | None = None
    kept_incumbent: bool = False
    paired_win_vs_incumbent: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "n_folds": self.n_folds,
            "seed": self.seed,
            "ranking": [dict(r) for r in self.ranking],
            "best": self.best,
            "best_params": dict(self.best_params),
            "n_samples": self.n_samples,
            "notes": self.notes,
            "incumbent": self.incumbent,
            "kept_incumbent": self.kept_incumbent,
            "paired_win_vs_incumbent": self.paired_win_vs_incumbent,
        }


def paired_win(challenger: dict[int, float],
               incumbent: dict[int, float]) -> float | None:
    """Paired fold-by-fold win of challenger over incumbent.

    Lower metric is better. Returns mean(d) - SE(d) over the common
    fold indices where d = incumbent - challenger, or None when there
    are no common folds.
    """
    common = sorted(set(challenger) & set(incumbent))
    if not common:
        return None
    diffs = [incumbent[k] - challenger[k] for k in common]
    mean = sum(diffs) / len(diffs)
    var = sum((d - mean) ** 2 for d in diffs) / len(diffs)
    return mean - math.sqrt(var / len(diffs))


def _folds(n: int, n_folds: int, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    return [idx[i::n_folds] for i in range(n_folds)]


def auto_select(scores: Sequence[float], labels: Sequence[int],
                candidates: Sequence[str] | None = None,
                metric: str = "brier",
                n_folds: int = 5, seed: int = 0,
                refit_best: bool = True,
                incumbent: str | None = None,
                min_win: float = 0.0) -> SelectionResult:
    """Cross-validate candidate calibrators; return the ranked result.

    ``incumbent`` names the currently-deployed calibrator (it must be
    one of ``candidates``). When given, the argmin-mean challenger
    replaces it only if :func:`paired_win` over the incumbent clears
    ``min_win``; otherwise the incumbent is kept and ``best`` names
    the incumbent. ``"none"`` may be a candidate or the incumbent: it
    means "ship the raw scores".
    """
    _require_numpy()
    if metric not in _METRICS:
        raise CalibrationError(
            f"unknown metric {metric!r}; choose from {sorted(_METRICS)}")
    if n_folds < 2:
        raise CalibrationError("n_folds must be ≥ 2")
    names: list[str] = (list(candidates) if candidates is not None
                        else list(DEFAULT_CANDIDATES))
    if not names:
        raise CalibrationError("no candidate calibrators")
    if incumbent is not None and incumbent not in names:
        raise CalibrationError(
            f"incumbent {incumbent!r} is not among candidates")
    score_fn = _METRICS[metric]
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(labels), dtype=int)
    if s.shape != y.shape or s.size == 0:
        raise CalibrationError("scores/labels must be non-empty and aligned")
    if n_folds > s.size:
        raise CalibrationError("n_folds exceeds sample count")

    ranking: list[dict[str, Any]] = []
    fold_maps: dict[str, dict[int, float]] = {}
    for name in names:
        fold_scores: dict[int, float] = {}
        if name == NONE_CANDIDATE:
            for fi, fold in enumerate(_folds(s.size, n_folds, seed)):
                raw = [min(1.0, max(0.0, float(v)))
                       for v in s[fold].tolist()]
                fold_scores[fi] = score_fn(y[fold].tolist(), raw)
        else:
            cls = CalibratorRegistry.get(name)  # raises on unknown names
            for fi, fold in enumerate(_folds(s.size, n_folds, seed)):
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
                fold_scores[fi] = score_fn(y[fold].tolist(), preds)
        if not fold_scores:
            raise CalibrationError(
                f"candidate {name!r}: no usable CV folds")
        vals = list(fold_scores.values())
        fold_maps[name] = fold_scores
        ranking.append({
            "name": name,
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
            "folds": float(len(vals)),
        })
    ranking.sort(key=lambda r: (r["mean"], r["name"]))
    argmin_best = ranking[0]["name"]

    best = argmin_best
    kept_incumbent = False
    win: float | None = None
    if incumbent is not None:
        if argmin_best == incumbent:
            kept_incumbent = True  # already the best: trivially kept
        else:
            win = paired_win(fold_maps[argmin_best], fold_maps[incumbent])
            if win is None or win < min_win:
                best = incumbent
                kept_incumbent = True

    best_params: dict[str, Any] = {}
    if refit_best and best != NONE_CANDIDATE:
        winner = CalibratorRegistry.get(best)()
        winner.fit(s.tolist(), y.tolist())
        best_params = winner.get_params()
    notes = f"lower {metric} is better; held-out means over CV folds"
    if incumbent is not None:
        if kept_incumbent:
            detail = (f"paired win {win:.6f} < {min_win}"
                      if win is not None else "already the argmin mean")
            notes += f"; incumbent {incumbent!r} kept ({detail})"
        else:
            win_text = f"{win:.6f}" if win is not None else "n/a"
            notes += (f"; challenger beat incumbent {incumbent!r} "
                      f"(paired win {win_text} >= {min_win})")
    return SelectionResult(
        metric=metric, n_folds=n_folds, seed=seed,
        ranking=ranking, best=best, best_params=best_params,
        n_samples=int(s.size),
        notes=notes,
        incumbent=incumbent,
        kept_incumbent=kept_incumbent,
        paired_win_vs_incumbent=win,
    )
