"""Threshold tuner. Slice 454.

Attacks a real weakness: HugrGate's decision thresholds (the policy's
``minimum_probability``, per-option gates in :mod:`hugrgate.threshold`)
are hand-set constants. This tuner sweeps a threshold parameter over a
grid, evaluates each candidate with stratified k-fold cross-validation
on labeled score data, and proposes the winner — but only when the
held-out win clears ``min_delta`` over the current value.

Metric choices (all computed on the held-out folds):

- ``f1``: harmonic mean of precision/recall at the threshold;
- ``accuracy``: plain correctness;
- ``youden``: TPR - FPR (best operating point on the ROC);
- ``f_beta:<b>``: recall-weighted F score.

The tuner is deliberately conservative: it maximizes the *mean*
held-out metric minus one standard error (the "one-SE rule"), so it
prefers thresholds that are robust, not just lucky on one fold.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner, kfold_indices, linspace
from hugrgate.errors import TunerError

__all__ = ["ThresholdTuner", "threshold_metric"]


def _counts(scores: Sequence[float], labels: Sequence[int],
            threshold: float) -> tuple[int, int, int, int]:
    tp = fp = tn = fn = 0
    for s, lab in zip(scores, labels, strict=True):
        pred = 1 if s >= threshold else 0
        if pred == 1 and lab == 1:
            tp += 1
        elif pred == 1:
            fp += 1
        elif lab == 1:
            fn += 1
        else:
            tn += 1
    return tp, fp, tn, fn


def threshold_metric(metric: str, scores: Sequence[float],
                     labels: Sequence[int], threshold: float) -> float:
    """Score one threshold on labeled data."""
    tp, fp, tn, fn = _counts(scores, labels, threshold)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if metric == "accuracy":
        n = tp + fp + tn + fn
        return (tp + tn) / n if n else 0.0
    if metric == "precision":
        return precision
    if metric == "recall":
        return recall
    if metric == "youden":
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        return recall - fpr
    if metric == "f1" or metric.startswith("f_beta:"):
        beta = 1.0
        if metric.startswith("f_beta:"):
            try:
                beta = float(metric.split(":", 1)[1])
            except ValueError as exc:
                raise TunerError(f"bad f_beta spec {metric!r}") from exc
            if beta <= 0:
                raise TunerError(f"bad f_beta spec {metric!r}")
        b2 = beta * beta
        denom = (1 + b2) * tp + b2 * fn + fp
        return ((1 + b2) * tp / denom) if denom else 0.0
    raise TunerError(f"unknown threshold metric {metric!r}")


@dataclass
class ThresholdTuner(BaseTuner):
    """Sweep a float threshold parameter on labeled score data."""

    name: str = "threshold_tuner"
    dataset: Sequence[tuple[float, int]] = field(default_factory=list)
    metric: str = "f1"
    n_folds: int = 5
    grid: int = 41

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("threshold tuner needs a param name")
        if not self.objective_id:
            raise TunerError("threshold tuner needs an objective_id")
        if len(self.dataset) < 2 * self.n_folds:
            raise TunerError("dataset too small for k-fold",
                             n=len(self.dataset), folds=self.n_folds)
        for s, lab in self.dataset:
            if not isinstance(s, (int, float)) or not math.isfinite(s):
                raise TunerError("scores must be finite numbers")
            if lab not in (0, 1):
                raise TunerError("labels must be 0/1")

    def _fold_scores(self, thresholds: Sequence[float],
                     seed: int) -> dict[float, list[float]]:
        scores = [s for s, _ in self.dataset]
        labels = [lab for _, lab in self.dataset]
        per_t: dict[float, list[float]] = {t: [] for t in thresholds}
        for _train_idx, test_idx in kfold_indices(len(self.dataset), labels,
                                                 self.n_folds, seed):
            ts = [scores[i] for i in test_idx]
            tl = [labels[i] for i in test_idx]
            for t in thresholds:
                per_t[t].append(threshold_metric(self.metric, ts, tl, t))
        return per_t

    @staticmethod
    def _robust(vals: Sequence[float]) -> float:
        """Held-out mean minus one standard error (one-SE rule)."""
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        return mean - math.sqrt(var / len(vals))

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "float":
            raise TunerError("threshold tuner needs a float param",
                             param=self.param, dtype=param.dtype)
        lo, hi = float(param.lo), float(param.hi)  # type: ignore[arg-type]
        thresholds = linspace(lo, hi, self.grid)
        per_t = self._fold_scores(thresholds, ctx.seed)
        robust = self._robust
        best = max(thresholds, key=lambda t: robust(per_t[t]))
        current = float(ctx.store.get(self.param))
        scores = [s for s, _ in self.dataset]
        labels = [lab for _, lab in self.dataset]
        # Baseline through the SAME k-fold protocol as the candidates.
        base_vals = []
        for _t, test_idx in kfold_indices(
                len(self.dataset), labels, self.n_folds, ctx.seed):
            ts = [scores[i] for i in test_idx]
            tl = [labels[i] for i in test_idx]
            base_vals.append(threshold_metric(self.metric, ts, tl, current))
        # Paired significance: the win must survive fold-by-fold.
        # d_k = best_k - base_k on the same held-out fold; propose only
        # when mean(d) - SE(d) clears min_delta. This discounts the
        # selection bias of picking the best of `grid` thresholds.
        diffs = [b - v for b, v in zip(per_t[best], base_vals, strict=True)]
        mean_d = sum(diffs) / len(diffs)
        var_d = sum((d - mean_d) ** 2 for d in diffs) / len(diffs)
        paired_win = mean_d - math.sqrt(var_d / len(diffs))
        baseline = robust(base_vals)
        evidence: dict[str, Any] = {
            "metric": self.metric,
            "n_folds": self.n_folds,
            "grid": self.grid,
            "best_threshold": best,
            "best_robust_score": robust(per_t[best]),
            "baseline_robust_score": baseline,
            "paired_win_mean_minus_se": paired_win,
            "per_fold_best": per_t[best],
            "note": "baseline and candidates share one stratified k-fold "
                    "protocol; proposal requires the paired fold-by-fold "
                    "win (mean - SE) to clear min_delta",
        }
        if paired_win < self.min_delta:
            return None
        return self._propose(ctx, {self.param: best}, baseline,
                             robust(per_t[best]), evidence)
