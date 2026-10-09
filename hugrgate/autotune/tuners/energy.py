"""Energy-aware tuner. Slice 463.

Quality costs energy. This tuner chooses among discrete operating
choices (backends, model sizes, feature flags) using *measured*
per-decision energy samples and quality scores — never assumed
numbers.

Two modes:

- ``budget``: maximize mean quality subject to mean energy per
  decision <= ``energy_budget_j``;
- ``efficiency``: maximize mean quality per joule.

Energy samples are joules-per-decision measured by the operator's
power instrumentation (RAPL, INA rails, or a calibrated power
model). The tuner does not invent them: every figure in the proposal
evidence is computed from the input samples, and the explicit
baseline — the *current* choice measured on the same samples — is
reported alongside the tuned choice. Re-running with the same seed
and samples reproduces the artifact exactly.

The tunable parameter is a str param naming the active choice.
Choices with fewer than ``min_samples`` are excluded (a mean over
three samples is not a measurement).
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

__all__ = ["EnergyAwareTuner"]


@dataclass
class EnergyAwareTuner(BaseTuner):
    """Pick the operating choice that best trades quality for energy."""

    name: str = "energy_aware_tuner"
    choices: Sequence[str] = field(default_factory=list)
    energy_j: Mapping[str, Sequence[float]] = field(default_factory=dict)
    quality: Mapping[str, Sequence[float]] = field(default_factory=dict)
    mode: str = "budget"  # or "efficiency"
    energy_budget_j: float = 1.0
    min_samples: int = 20

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("energy tuner needs a param name")
        if not self.objective_id:
            raise TunerError("energy tuner needs an objective_id")
        if len(self.choices) < 2:
            raise TunerError("need at least 2 choices")
        if len(set(self.choices)) != len(self.choices):
            raise TunerError("duplicate choices")
        if self.mode not in ("budget", "efficiency"):
            raise TunerError("mode must be budget/efficiency", mode=self.mode)
        if self.energy_budget_j <= 0:
            raise TunerError("energy budget must be positive")
        for ch in self.choices:
            for samples, what in ((self.energy_j.get(ch), "energy"),
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
        """(mean_energy, se_energy, mean_quality, se_quality)."""
        e = list(self.energy_j[choice])
        q = list(self.quality[choice])
        me, mq = statistics.fmean(e), statistics.fmean(q)
        se_e = statistics.stdev(e) / math.sqrt(len(e)) if len(e) > 1 else 0.0
        se_q = statistics.stdev(q) / math.sqrt(len(q)) if len(q) > 1 else 0.0
        return me, se_e, mq, se_q

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "str":
            raise TunerError("energy tuner needs a str param",
                             param=self.param)
        stats = {ch: self._stats(ch) for ch in self.choices}
        if self.mode == "budget":
            # Conservative: a choice is budget-feasible only when its
            # mean + 1 SE fits the budget (don't gamble on noise).
            feasible = [ch for ch in self.choices
                        if stats[ch][0] + stats[ch][1] <= self.energy_budget_j]
            if not feasible:
                return None
            best = max(feasible, key=lambda ch: stats[ch][2])
            primary = {ch: stats[ch][2] for ch in self.choices}
            metric_name = "mean_quality"
        else:
            feasible = list(self.choices)
            best = max(feasible,
                       key=lambda ch: stats[ch][2] / max(stats[ch][0], 1e-12))
            primary = {ch: stats[ch][2] / max(stats[ch][0], 1e-12)
                       for ch in self.choices}
            metric_name = "quality_per_joule"
        current = str(ctx.store.get(self.param))
        if current not in stats:
            raise TunerError("current choice has no measurements",
                             current=current)
        # An over-budget incumbent is not a baseline to beat — it is a
        # violation to escape. Score it at -inf so any feasible choice
        # wins on the constrained objective.
        current_feasible = (current in feasible)
        base_primary = (primary[current] if current_feasible
                        else float("-inf"))
        evidence: dict[str, Any] = {
            "mode": self.mode,
            "energy_budget_j": self.energy_budget_j,
            "metric": metric_name,
            "feasible_choices": feasible,
            "current_feasible": current_feasible,
            "measured": {
                ch: {"mean_energy_j": stats[ch][0],
                     "se_energy_j": stats[ch][1],
                     "mean_quality": stats[ch][2],
                     "se_quality": stats[ch][3],
                     "n_energy": len(self.energy_j[ch]),
                     "n_quality": len(self.quality[ch])}
                for ch in self.choices
            },
            "baseline": {"choice": current,
                         "primary": base_primary},
            "tuned": {"choice": best, "primary": primary[best]},
            "note": ("all figures are means over the provided samples; "
                     "budget feasibility uses mean + 1 SE (conservative); "
                     "an infeasible incumbent scores -inf"),
        }
        if best == current:
            return None
        return self._propose(ctx, {self.param: best}, base_primary,
                             primary[best], evidence)
