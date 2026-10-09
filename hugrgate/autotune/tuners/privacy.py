"""Privacy-constrained tuner. Slice 465.

Optimization must never buy utility with privacy it does not own.
This tuner chooses among operating choices (telemetry verbosity,
retention windows, redaction levels, DP-noised vs raw features)
subject to two hard privacy fences:

1. **Classification ceiling**: every choice declares the privacy
   class of the data it touches (the :mod:`hugrgate.privacy` ladder:
   public < standard < sensitive < strict < forbidden). A choice is
   eligible only when its class is at or below the deployment's
   ``max_privacy_class`` (from ``ctx.data``) — checked with
   :func:`hugrgate.privacy.class_rank`, so the ladder's ordering
   stays load-bearing in exactly one place.
2. **Epsilon budget**: every choice declares its differential-privacy
   spend (0 = no personal data leaves the enclave); the chosen
   choice's epsilon must fit ``epsilon_budget``.

Modes: ``budget`` maximizes mean measured utility under the fences;
``minimize`` minimizes epsilon spend subject to the utility
guarantee mean - 1.96*SE >= ``utility_floor``. An infeasible
incumbent scores -inf. Evidence records the class and epsilon
accounting per choice — the privacy audit trail for the decision.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.errors import TunerError
from hugrgate.privacy import PRIVACY_CLASS_ORDER, class_rank

__all__ = ["PrivacyConstrainedTuner"]


@dataclass
class PrivacyConstrainedTuner(BaseTuner):
    """Maximize utility without crossing privacy fences."""

    name: str = "privacy_constrained_tuner"
    choices: Sequence[str] = field(default_factory=list)
    privacy_class: Mapping[str, str] = field(default_factory=dict)
    epsilon: Mapping[str, float] = field(default_factory=dict)
    utility: Mapping[str, Sequence[float]] = field(default_factory=dict)
    mode: str = "budget"  # or "minimize"
    epsilon_budget: float = 1.0
    utility_floor: float = 0.8
    min_samples: int = 20

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("privacy tuner needs a param name")
        if not self.objective_id:
            raise TunerError("privacy tuner needs an objective_id")
        if len(self.choices) < 2:
            raise TunerError("need at least 2 choices")
        if len(set(self.choices)) != len(self.choices):
            raise TunerError("duplicate choices")
        if self.mode not in ("budget", "minimize"):
            raise TunerError("mode must be budget/minimize", mode=self.mode)
        if self.epsilon_budget < 0:
            raise TunerError("epsilon budget must be >= 0")
        if not 0.0 < self.utility_floor < 1.0:
            raise TunerError("utility floor must be in (0, 1)")
        for ch in self.choices:
            pc = self.privacy_class.get(ch)
            if pc not in PRIVACY_CLASS_ORDER:
                raise TunerError("unknown privacy class", choice=ch,
                                 privacy_class=pc)
            ep = self.epsilon.get(ch)
            # +inf means "unbounded spend" (never fits a finite budget)
            if ep is None or not isinstance(ep, (int, float)) \
                    or math.isnan(ep) or ep < 0:
                raise TunerError("epsilon must be >= 0 (+inf allowed)",
                                 choice=ch)
            us = self.utility.get(ch)
            if us is None or len(us) < self.min_samples:
                raise TunerError(
                    f"choice {ch!r} needs >= {self.min_samples} "
                    "utility samples")
            if any((not isinstance(v, (int, float))
                    or not math.isfinite(v)) for v in us):
                raise TunerError("utility samples must be finite",
                                 choice=ch)

    def _eligible(self, ctx: TuningContext) -> tuple[list[str], str]:
        ceiling = str(ctx.data.get("max_privacy_class", "forbidden"))
        if ceiling not in PRIVACY_CLASS_ORDER:
            raise TunerError("bad max_privacy_class in ctx.data",
                             ceiling=ceiling)
        ceil_rank = class_rank(ceiling)
        eligible = [ch for ch in self.choices
                    if class_rank(self.privacy_class[ch]) <= ceil_rank
                    and self.epsilon[ch] <= self.epsilon_budget]
        return eligible, ceiling

    def _mean_se(self, choice: str) -> tuple[float, float]:
        us = list(self.utility[choice])
        mean = statistics.fmean(us)
        se = statistics.stdev(us) / math.sqrt(len(us)) if len(us) > 1 else 0.0
        return mean, se

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "str":
            raise TunerError("privacy tuner needs a str param",
                             param=self.param)
        eligible, ceiling = self._eligible(ctx)
        stats = {ch: self._mean_se(ch) for ch in self.choices}
        if self.mode == "budget":
            feasible = eligible
            if not feasible:
                return None
            best = max(feasible, key=lambda ch: stats[ch][0])
            primary = {ch: stats[ch][0] for ch in self.choices}
            metric_name = "mean_utility"
        else:
            feasible = [ch for ch in eligible
                        if stats[ch][0] - 1.96 * stats[ch][1]
                        >= self.utility_floor]
            if not feasible:
                return None
            best = min(feasible, key=lambda ch: self.epsilon[ch])
            primary = {ch: -self.epsilon[ch] for ch in self.choices}
            metric_name = "neg_epsilon"
        current = str(ctx.store.get(self.param))
        if current not in stats:
            raise TunerError("current choice has no measurements",
                             current=current)
        current_feasible = current in feasible
        base_primary = (primary[current] if current_feasible
                        else float("-inf"))
        evidence: dict[str, Any] = {
            "mode": self.mode,
            "epsilon_budget": self.epsilon_budget,
            "max_privacy_class": ceiling,
            "metric": metric_name,
            "feasible_choices": feasible,
            "current_feasible": current_feasible,
            "accounting": {
                ch: {"privacy_class": self.privacy_class[ch],
                     "epsilon": self.epsilon[ch],
                     "mean_utility": stats[ch][0],
                     "se_utility": stats[ch][1],
                     "n": len(self.utility[ch])}
                for ch in self.choices
            },
            "baseline": {"choice": current, "primary": base_primary},
            "tuned": {"choice": best, "primary": primary[best]},
            "note": ("classification checked against the hugrgate.privacy "
                     "ladder; epsilon is DP spend, 0 = no personal data"),
        }
        if best == current:
            return None
        return self._propose(ctx, {self.param: best}, base_primary,
                             primary[best], evidence)
