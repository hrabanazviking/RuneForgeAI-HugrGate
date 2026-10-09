"""Confidence-gate tuner. Slice 455.

The abstention gate ("answer only when confidence >= tau") trades
*coverage* (fraction answered) against *selective accuracy* (accuracy
on the answered). This tuner learns tau from labeled
(confidence, correct) pairs with an honest statistical guarantee:

- ``accuracy_floor`` mode: maximize coverage subject to the
  **Wilson lower bound** of the selective accuracy staying above a
  floor at confidence level ``1 - alpha``;
- ``coverage_target`` mode: maximize selective accuracy subject to
  coverage staying above a target.

Protocol (all seeded, all deterministic):

1. stratified 70/30 train/validation split on correctness;
2. on train, sweep tau over a grid; keep the feasible set per mode;
3. pick the feasible tau maximizing the primary metric (ties break
   toward the *lower* tau — less abstention for equal quality);
4. **validate on the held-out split**: the guarantee is checked on
   data the selection never saw. A proposal is made only if the
   held-out check passes *and* the primary metric beats the current
   tau by ``min_delta``.

Metric/coverage assumptions (reported in every proposal's evidence):

- confidence scores are comparable across samples (a higher score
  means more likely correct — the tuner does not recalibrate);
- the validation split is i.i.d. with deployment traffic; under
  distribution shift the Wilson bound does not transfer;
- ``correct`` labels are ground truth, not model self-reports.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner, linspace, seeded_rng
from hugrgate.errors import TunerError

__all__ = ["ConfidenceGateTuner", "wilson_lower_bound"]


def wilson_lower_bound(successes: int, trials: int,
                       alpha: float = 0.05) -> float:
    """Wilson score lower bound for a binomial proportion."""
    if trials <= 0:
        return 0.0
    if not 0.0 < alpha < 1.0:
        raise TunerError("alpha must be in (0, 1)", alpha=alpha)
    # z for common alphas; fall back to the normal approximation
    # via the inverse Mills-style refinement for other values.
    z = {0.10: 1.6448536269514722, 0.05: 1.959963984540054,
         0.01: 2.5758293035489004}.get(alpha)
    if z is None:
        z = _normal_quantile(1.0 - alpha / 2.0)
    p = successes / trials
    denom = 1.0 + z * z / trials
    center = p + z * z / (2.0 * trials)
    margin = z * math.sqrt(p * (1.0 - p) / trials
                           + z * z / (4.0 * trials * trials))
    return max(0.0, (center - margin) / denom)


def _normal_quantile(p: float) -> float:
    """Acklam's approximation of the standard normal quantile."""
    if not 0.0 < p < 1.0:
        raise TunerError("p must be in (0, 1)", p=p)
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q
                + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q
                 + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r
            + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r
                            + b[4]) * r + 1.0)


def _coverage_and_accuracy(data: Sequence[tuple[float, bool]],
                           tau: float) -> tuple[float, float, int, int]:
    """(coverage, selective_accuracy, n_answered, n_correct)."""
    answered = [(c, ok) for c, ok in data if c >= tau]
    n = len(answered)
    if n == 0:
        return 0.0, 0.0, 0, 0
    correct = sum(1 for _, ok in answered if ok)
    return n / len(data), correct / n, n, correct


@dataclass
class ConfidenceGateTuner(BaseTuner):
    """Learn the abstention threshold tau with a statistical guarantee."""

    name: str = "confidence_gate_tuner"
    dataset: Sequence[tuple[float, bool]] = field(default_factory=list)
    mode: str = "accuracy_floor"  # or "coverage_target"
    floor: float = 0.8  # selective-accuracy floor (accuracy_floor mode)
    target: float = 0.8  # coverage target (coverage_target mode)
    alpha: float = 0.05
    grid: int = 41
    train_fraction: float = 0.7

    def __post_init__(self) -> None:
        if not self.param:
            raise TunerError("gate tuner needs a param name")
        if not self.objective_id:
            raise TunerError("gate tuner needs an objective_id")
        if self.mode not in ("accuracy_floor", "coverage_target"):
            raise TunerError("mode must be accuracy_floor/coverage_target",
                             mode=self.mode)
        if not 0.0 < self.floor < 1.0 or not 0.0 < self.target < 1.0:
            raise TunerError("floor/target must be in (0, 1)")
        if not 0.0 < self.alpha < 1.0:
            raise TunerError("alpha must be in (0, 1)")
        if len(self.dataset) < 40:
            raise TunerError("dataset too small for split validation",
                             n=len(self.dataset))
        for c, ok in self.dataset:
            if not isinstance(c, (int, float)) or not 0.0 <= c <= 1.0:
                raise TunerError("confidences must be in [0, 1]")
            if not isinstance(ok, bool):
                raise TunerError("labels must be bool")

    def _split(self, seed: int) -> tuple[list, list]:
        rng = seeded_rng(seed)
        pos = [d for d in self.dataset if d[1]]
        neg = [d for d in self.dataset if not d[1]]
        rng.shuffle(pos)
        rng.shuffle(neg)
        kpos = max(1, int(len(pos) * self.train_fraction))
        kneg = max(1, int(len(neg) * self.train_fraction))
        train = pos[:kpos] + neg[:kneg]
        valid = pos[kpos:] + neg[kneg:]
        rng.shuffle(train)
        rng.shuffle(valid)
        return train, valid

    def tune(self, ctx: TuningContext) -> Proposal | None:
        param = ctx.store.describe(self.param)
        if param.dtype != "float":
            raise TunerError("gate tuner needs a float param",
                             param=self.param)
        lo, hi = float(param.lo), float(param.hi)  # type: ignore[arg-type]
        train, valid = self._split(ctx.seed)
        taus = linspace(max(lo, 0.0), min(hi, 1.0), self.grid)

        def feasible_tr(tau: float) -> bool:
            cov, _acc, n, k = _coverage_and_accuracy(train, tau)
            if n == 0:
                return False
            if self.mode == "accuracy_floor":
                return (wilson_lower_bound(k, n, self.alpha) >= self.floor
                        and cov > 0.0)
            return cov >= self.target

        feasible = [t for t in taus if feasible_tr(t)]
        if not feasible:
            return None
        def _key(tau: float) -> tuple[float, float]:
            cov, acc, _, _ = _coverage_and_accuracy(train, tau)
            primary = cov if self.mode == "accuracy_floor" else acc
            return (primary, -tau)

        best = max(feasible, key=_key)

        # Held-out validation of the guarantee.
        cov_v, acc_v, n_v, k_v = _coverage_and_accuracy(valid, best)
        lb_v = wilson_lower_bound(k_v, n_v, self.alpha)
        current = float(ctx.store.get(self.param))
        cov_c, _acc_c, n_c, k_c = _coverage_and_accuracy(valid, current)
        lb_c = wilson_lower_bound(k_c, n_c, self.alpha)

        if self.mode == "accuracy_floor":
            if lb_v < self.floor:
                return None  # guarantee failed on held-out data
            primary, base_primary = cov_v, cov_c
            metric_name = "coverage"
        else:
            if cov_v < self.target - 1e-9:
                return None
            primary, base_primary = lb_v, lb_c
            metric_name = "selective_accuracy_wilson_lb"

        evidence: dict[str, Any] = {
            "mode": self.mode,
            "alpha": self.alpha,
            "floor": self.floor,
            "target": self.target,
            "best_tau": best,
            "heldout_coverage": cov_v,
            "heldout_selective_accuracy": acc_v,
            "heldout_wilson_lb": lb_v,
            "heldout_n": n_v,
            "baseline_tau": current,
            "baseline_heldout_coverage": cov_c,
            "baseline_heldout_wilson_lb": lb_c,
            "primary_metric": metric_name,
            "assumptions": (
                "confidence scores are comparable across samples; "
                "validation split is i.i.d. with deployment traffic "
                "(guarantee does not transfer under shift); "
                "labels are ground truth"),
        }
        return self._propose(ctx, {self.param: best}, base_primary,
                             primary, evidence)
