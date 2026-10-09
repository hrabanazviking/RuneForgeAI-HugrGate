"""Cost-aware tuner. Slice 464.

Money is the other budget. This tuner chooses among priced operating
choices (backends, API tiers, model endpoints) from *measured*
per-decision cost samples (dollars, from billing/telemetry — never
assumed) and quality samples.

Two modes:

- ``budget``: maximize mean quality subject to mean + 1 SE cost <=
  ``cost_budget`` (conservative: no gambling on noisy cost means);
- ``floor``: minimize mean cost subject to the quality guarantee
  ``mean - 1.96*SE >= quality_floor`` — the operator's quality bar
  holds with ~95% confidence on the measured samples.

An over-budget (or under-floor) incumbent scores -inf: a violation
to escape, not a baseline to beat. The tunable parameter is a str
param naming the active choice; the proposal evidence is the full
measured comparison, re-derivable from the input samples.
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

__all__ = ["CostAwareTuner"]


@dataclass
class CostAwareTuner(BaseTuner):
    """Pick the priced choice that best trades quality for money."""

    name: str = "cost_aware_tuner"
    choices: Sequence[str] = field(default_factory=list)
    cost: Mapping[str, Sequence[float]] = field(default_factory=dict)
    quality: Mapping[str, Sequence[float]] = field(default_factory=dict)
    mode: str = "budget"  # or "floor"
    cost_budget: float = 1.0  # dollars per decision (budget mode)
    quality_floor: float = 0.8  # (floor mode)
    min_samples: int = 20

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("cost tuner needs a param name")
        if not self.objective_id:
            raise TunerError("cost tuner needs an objective_id")
        if len(self.choices) < 2:
            raise TunerError("need at least 2 choices")
        if len(set(self.choices)) != len(self.choices):
            raise TunerError("duplicate choices")
        if self.mode not in ("budget", "floor"):
            raise TunerError("mode must be budget/floor", mode=self.mode)
        if self.cost_budget <= 0:
            raise TunerError("cost budget must be positive")
        if not 0.0 < self.quality_floor < 1.0:
            raise TunerError("quality floor must be in (0, 1)")
        for ch in self.choices:
            for samples, what in ((self.cost.get(ch), "cost"),
                                  (self.quality.get(ch), "quality")):
                if samples is None or len(samples) < self.min_samples:
                    raise TunerError(
                        f"choice {ch!r} needs >= {self.min_samples} "
                        f"{what} samples")
                if any((not isinstance(v, (int, float))
                        or not math.isfinite(v) or v < 0) for v in samples):
                    raise TunerError(
                        f"{what} samples must be finite >= 0", choice=ch)

    def _stats(self, choice: str) -> tuple[float, float, float, float]:
        c = list(self.cost[choice])
        q = list(self.quality[choice])
        mc, mq = statistics.fmean(c), statistics.fmean(q)
        se_c = statistics.stdev(c) / math.sqrt(len(c)) if len(c) > 1 else 0.0
        se_q = statistics.stdev(q) / math.sqrt(len(q)) if len(q) > 1 else 0.0
        return mc, se_c, mq, se_q

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "str":
            raise TunerError("cost tuner needs a str param",
                             param=self.param)
        stats = {ch: self._stats(ch) for ch in self.choices}
        if self.mode == "budget":
            feasible = [ch for ch in self.choices
                        if stats[ch][0] + stats[ch][1] <= self.cost_budget]
            if not feasible:
                return None
            best = max(feasible, key=lambda ch: stats[ch][2])
            primary = {ch: stats[ch][2] for ch in self.choices}
            metric_name = "mean_quality"
        else:
            feasible = [ch for ch in self.choices
                        if stats[ch][2] - 1.96 * stats[ch][3]
                        >= self.quality_floor]
            if not feasible:
                return None
            best = min(feasible, key=lambda ch: stats[ch][0])
            primary = {ch: -stats[ch][0] for ch in self.choices}
            metric_name = "neg_mean_cost"
        current = str(ctx.store.get(self.param))
        if current not in stats:
            raise TunerError("current choice has no measurements",
                             current=current)
        current_feasible = current in feasible
        base_primary = (primary[current] if current_feasible
                        else float("-inf"))
        evidence: dict[str, Any] = {
            "mode": self.mode,
            "cost_budget": self.cost_budget,
            "quality_floor": self.quality_floor,
            "metric": metric_name,
            "feasible_choices": feasible,
            "current_feasible": current_feasible,
            "measured": {
                ch: {"mean_cost": stats[ch][0], "se_cost": stats[ch][1],
                     "mean_quality": stats[ch][2],
                     "se_quality": stats[ch][3],
                     "n": len(self.cost[ch])}
                for ch in self.choices
            },
            "baseline": {"choice": current, "primary": base_primary},
            "tuned": {"choice": best, "primary": primary[best]},
            "note": ("costs are measured dollars per decision; floor mode "
                     "requires mean - 1.96*SE >= floor (~95% confidence)"),
        }
        if best == current:
            return None
        return self._propose(ctx, {self.param: best}, base_primary,
                             primary[best], evidence)
