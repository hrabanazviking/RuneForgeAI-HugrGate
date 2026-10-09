"""Calibration selector tuner. Slice 461.

Wraps the hardened :func:`hugrgate.calibration.autoselect.auto_select`
(slice 092 + slice 461) as an autotune tuner: the tunable parameter is
the *name* of the deployed calibrator (a str param whose choices
cover the candidate catalog plus ``"none"``), and the current value is
treated as the incumbent. A challenger is proposed only when its
paired fold-by-fold win over the incumbent clears ``min_win`` —
otherwise the tuner stays silent ("do no harm").

Requires numpy (the ``ml`` extra); without it the tuner raises and
the controller isolates it like any crashing tuner.

Statistical behavior, validated on controlled data (see tests): on
systematically miscalibrated scores the selector moves off ``"none"``
to a calibrator that lowers held-out ECE; on already-calibrated
scores it keeps ``"none"``. Assumptions recorded in every proposal's
evidence: scores and labels are i.i.d. with deployment traffic; the
selection metric (Brier/log-loss/ECE) matches the operator's notion
of "calibrated"; the refit winner is deployed, not the fold models.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.calibration.autoselect import NONE_CANDIDATE, auto_select
from hugrgate.errors import TunerError

__all__ = ["CalibrationSelectorTuner"]


@dataclass
class CalibrationSelectorTuner(BaseTuner):
    """Select the calibrator by cross-validated proper scoring."""

    name: str = "calibration_selector_tuner"
    scores: Sequence[float] = field(default_factory=list)
    labels: Sequence[int] = field(default_factory=list)
    candidates: Sequence[str] | None = None
    metric: str = "brier"
    n_folds: int = 5
    min_win: float = 0.0

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("calibration tuner needs a param name")
        if not self.objective_id:
            raise TunerError("calibration tuner needs an objective_id")
        if len(self.scores) != len(self.labels) or len(self.scores) < 50:
            raise TunerError("need >= 50 aligned score/label pairs",
                             n=len(self.scores))

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "str":
            raise TunerError("calibration tuner needs a str param",
                             param=self.param)
        current = str(ctx.store.get(self.param))
        from hugrgate.calibration.autoselect import DEFAULT_CANDIDATES
        base = (list(self.candidates) if self.candidates is not None
                else list(DEFAULT_CANDIDATES))
        candidates: list[str] = ([*base, NONE_CANDIDATE]
                                 if NONE_CANDIDATE not in base else base)
        if current not in candidates:
            raise TunerError("current calibrator not among candidates",
                             current=current)
        result = auto_select(
            list(self.scores), list(self.labels),
            candidates=candidates, metric=self.metric,
            n_folds=self.n_folds, seed=ctx.seed,
            incumbent=current, min_win=self.min_win)
        if result.best == current:
            return None
        means = {r["name"]: r["mean"] for r in result.ranking}
        evidence: dict[str, Any] = {
            "metric": self.metric,
            "n_folds": self.n_folds,
            "candidates": [r["name"] for r in result.ranking],
            "ranking": result.ranking,
            "paired_win_vs_incumbent": result.paired_win_vs_incumbent,
            "best_params": result.best_params,
            "assumptions": (
                "scores/labels i.i.d. with deployment traffic; "
                f"{self.metric} matches the operator's calibration goal; "
                "the refit-on-full-data winner is what gets deployed"),
        }
        # Lower metric is better: negate so higher is better.
        return self._propose(ctx, {self.param: result.best},
                             -means[current], -means[result.best],
                             evidence)
