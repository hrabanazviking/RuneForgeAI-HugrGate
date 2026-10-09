"""Bootstrap confidence intervals for evaluation metrics. Slice 358.

Point estimates lie by omission: an accuracy of 0.83 on 40 items is a
different claim than on 40,000.  This module adds percentile bootstrap
CIs over per-item outcomes, reusing the v1 metric functions from
:mod:`hugrgate.bench`:

- :func:`bootstrap_metric_ci` — CI for any metric computed from
  ``(expected, DecisionResult)`` pairs;
- :func:`bootstrap_backend_ci` — lab-friendly: evaluates one backend
  over a dataset once, then bootstraps the named metric.

Resampling uses a dedicated ``random.Random(seed)`` — deterministic
for a fixed seed, invisible to the global RNG.  The percentile method
is used (simple, honest, distribution-free); BCa bias correction is
deliberately out of scope for this slice.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate import bench as _bench
from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "BootstrapCI",
    "bootstrap_backend_ci",
    "bootstrap_metric_ci",
]

#: (expected, result) pairs as produced by evaluation loops.
#: ``None`` results are abstentions, filtered before metric evaluation.
Pairs = list[tuple[Any, DecisionResult | None]]

#: Scored pairs: abstentions removed.
ScoredPairs = list[tuple[Any, DecisionResult]]

#: A metric over scored pairs + spec, mirroring the bench.py signatures.
MetricFn = Callable[[ScoredPairs, DecisionSpec], float | None]

_MIN_BOOT = 100


def _builtin_metrics() -> dict[str, MetricFn]:
    return {
        "accuracy": lambda pairs, spec: _bench.accuracy(pairs),
        "brier_score": _bench.brier_score,
        "ece": lambda pairs, spec: _bench.expected_calibration_error(pairs),
    }


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        raise EvalError("cannot take a percentile of no values")
    k = (len(sorted_values) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


@dataclass
class BootstrapCI:
    """A point estimate with its percentile bootstrap interval."""

    metric: str
    estimate: float
    ci_low: float
    ci_high: float
    ci_level: float
    n_boot: int
    n_items: int
    seed: int

    @property
    def width(self) -> float:
        return self.ci_high - self.ci_low

    def contains(self, value: float) -> bool:
        return self.ci_low <= value <= self.ci_high

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "estimate": self.estimate,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_level": self.ci_level,
            "n_boot": self.n_boot,
            "n_items": self.n_items,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BootstrapCI:
        return cls(
            metric=data["metric"],
            estimate=data["estimate"],
            ci_low=data["ci_low"],
            ci_high=data["ci_high"],
            ci_level=data["ci_level"],
            n_boot=data["n_boot"],
            n_items=data["n_items"],
            seed=data["seed"],
        )


def bootstrap_metric_ci(
    pairs: Pairs,
    spec: DecisionSpec,
    metric: str | MetricFn = "accuracy",
    *,
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 0,
) -> BootstrapCI:
    """Percentile bootstrap CI for ``metric`` over ``pairs``."""
    rows = [(exp, res) for exp, res in pairs
            if exp is not None and res is not None]
    if len(rows) < 2:
        raise EvalError(
            f"bootstrap needs at least 2 scored items, got {len(rows)}"
        )
    if not 0.0 < ci < 1.0:
        raise EvalError(f"ci must be in (0, 1), got {ci}")
    if n_boot < _MIN_BOOT:
        raise EvalError(
            f"n_boot must be >= {_MIN_BOOT} for a meaningful interval, "
            f"got {n_boot}"
        )
    if isinstance(metric, str):
        name = metric
        try:
            metric_fn = _builtin_metrics()[metric]
        except KeyError:
            raise EvalError(
                f"unknown metric {metric!r}; builtins: "
                f"{sorted(_builtin_metrics())} (or pass a callable)",
                metric=metric,
            ) from None
    else:
        name = getattr(metric, "__name__", "custom")
        metric_fn = metric

    estimate = metric_fn(rows, spec)
    if estimate is None:
        raise EvalError(
            f"metric {name!r} is undefined on these items "
            "(no scored pairs)"
        )

    rng = random.Random(seed)
    n = len(rows)
    boot: list[float] = []
    for _ in range(n_boot):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        value = metric_fn(sample, spec)
        # A resample can hit an unscored corner (e.g. all-abstained
        # strata); skip it rather than poisoning the distribution.
        if value is not None:
            boot.append(value)
    if len(boot) < _MIN_BOOT:
        raise EvalError(
            f"only {len(boot)} usable bootstrap replicates; "
            "the metric is undefined on too many resamples"
        )
    boot.sort()
    alpha = 1.0 - ci
    return BootstrapCI(
        metric=name,
        estimate=float(estimate),
        ci_low=_percentile(boot, 100 * alpha / 2),
        ci_high=_percentile(boot, 100 * (1 - alpha / 2)),
        ci_level=ci,
        n_boot=len(boot),
        n_items=n,
        seed=seed,
    )


def _evaluate_pairs(
    gate: HugrGate,
    dataset: Mapping[str, Any],
    backend_name: str,
    policy: DecisionPolicy,
    max_items: int | None,
) -> tuple[Pairs, DecisionSpec]:
    """Evaluate every item once; abstentions become (expected, None)."""
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    pairs: Pairs = []
    for item in items:
        expected = item.get("expected")
        try:
            result = gate.decide(dict(item["state"]), spec, policy,
                                 backend_name=backend_name)
        except Abstention:
            pairs.append((expected, None))
        else:
            pairs.append((expected, result))
    return pairs, spec


def bootstrap_backend_ci(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backend: str,
    metric: str | MetricFn = "accuracy",
    *,
    policy: DecisionPolicy | None = None,
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 0,
    max_items: int | None = None,
) -> BootstrapCI:
    """Evaluate ``backend`` once, then bootstrap ``metric``'s CI."""
    pairs, spec = _evaluate_pairs(
        gate, dataset, backend, policy or DecisionPolicy(), max_items)
    return bootstrap_metric_ci(pairs, spec, metric,
                               n_boot=n_boot, ci=ci, seed=seed)
