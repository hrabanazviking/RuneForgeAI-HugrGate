"""Paired backend comparisons — A vs B on identical items. Slice 360.

The lab's head-to-head workhorse, composing slice 358 (bootstrap)
and slice 359 (significance) into one verdict:

- both backends evaluate the *same* items through the same gate;
- per-item scores (correctness for ``"accuracy"``, per-item squared
  error for ``"brier_score"``) feed a bootstrap CI on the *paired
  mean difference* and a paired permutation test;
- win/tie/loss counts say how often A outright beats B per item;
- the verdict is ``"a_better"`` / ``"b_better"`` / ``"tie"`` /
  ``"inconclusive"`` — never a bare p-value.

Only metrics with honest per-item decompositions are supported
(``"accuracy"``, ``"brier_score"``); anything else raises
:class:`EvalError` rather than pretending a paired test applies.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.core import HugrGate
from hugrgate.errors import Abstention, EvalError
from hugrgate.evlab.bootstrap import bootstrap_mean_ci
from hugrgate.evlab.significance import paired_permutation_test
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "BackendComparison",
    "compare_backends",
]

Pairs = Sequence[tuple[Any, DecisionResult | None]]


def _per_item_scores(
    pairs: Pairs, spec: DecisionSpec, metric: str
) -> list[float | None]:
    """Per-item score or None when the item is unscored (abstention)."""
    scores: list[float | None] = []
    for expected, result in pairs:
        if expected is None or result is None or result.value is None:
            scores.append(None)
            continue
        if metric == "accuracy":
            if isinstance(expected, list):
                hit = set(result.value or []) == set(expected)
            else:
                hit = result.value == expected
            scores.append(1.0 if hit else 0.0)
        elif metric == "brier_score":
            if spec.type in ("numeric", "multilabel") or not result.distribution:
                scores.append(None)
                continue
            total = 0.0
            for outcome in spec.value_space():
                truth = 1.0 if outcome == expected else 0.0
                total += (result.distribution.get(outcome, 0.0) - truth) ** 2
            scores.append(total)
        else:  # pragma: no cover - guarded by compare_backends
            raise EvalError(f"no per-item decomposition for {metric!r}")
    return scores


def _evaluate(
    gate: HugrGate,
    dataset: Mapping[str, Any],
    backend_name: str,
    policy: DecisionPolicy,
    max_items: int | None,
) -> tuple[Pairs, DecisionSpec]:
    spec = DecisionSpec.from_dict(dataset["spec"])
    items = list(dataset.get("items", []))
    if max_items is not None:
        items = items[:max_items]
    pairs: list[tuple[Any, DecisionResult | None]] = []
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


@dataclass
class BackendComparison:
    """Head-to-head comparison of two backends (slice 360)."""

    backend_a: str
    backend_b: str
    metric: str
    higher_better: bool
    n_items: int
    n_joint: int
    estimate_a: float
    estimate_b: float
    mean_diff: float  # a - b over jointly scored items
    diff_ci_low: float | None
    diff_ci_high: float | None
    p_value: float
    alpha: float
    wins_a: int
    wins_b: int
    ties: int
    verdict: str

    @property
    def significant(self) -> bool:
        return self.p_value < self.alpha

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_a": self.backend_a,
            "backend_b": self.backend_b,
            "metric": self.metric,
            "higher_better": self.higher_better,
            "n_items": self.n_items,
            "n_joint": self.n_joint,
            "estimate_a": self.estimate_a,
            "estimate_b": self.estimate_b,
            "mean_diff": self.mean_diff,
            "diff_ci_low": self.diff_ci_low,
            "diff_ci_high": self.diff_ci_high,
            "p_value": self.p_value,
            "alpha": self.alpha,
            "significant": self.significant,
            "wins_a": self.wins_a,
            "wins_b": self.wins_b,
            "ties": self.ties,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BackendComparison:
        return cls(
            backend_a=data["backend_a"],
            backend_b=data["backend_b"],
            metric=data["metric"],
            higher_better=data["higher_better"],
            n_items=data["n_items"],
            n_joint=data["n_joint"],
            estimate_a=data["estimate_a"],
            estimate_b=data["estimate_b"],
            mean_diff=data["mean_diff"],
            diff_ci_low=data["diff_ci_low"],
            diff_ci_high=data["diff_ci_high"],
            p_value=data["p_value"],
            alpha=data["alpha"],
            wins_a=data["wins_a"],
            wins_b=data["wins_b"],
            ties=data["ties"],
            verdict=data["verdict"],
        )


def compare_backends(
    dataset: Mapping[str, Any],
    gate: HugrGate,
    backend_a: str,
    backend_b: str,
    metric: str = "accuracy",
    *,
    policy: DecisionPolicy | None = None,
    seed: int = 0,
    n_boot: int = 2000,
    n_perm: int = 10000,
    alpha: float = 0.05,
    max_items: int | None = None,
) -> BackendComparison:
    """Compare two backends on identical items; return the verdict."""
    if metric not in ("accuracy", "brier_score"):
        raise EvalError(
            f"paired comparison supports 'accuracy' and 'brier_score', "
            f"got {metric!r}"
        )
    if backend_a == backend_b:
        raise EvalError("cannot compare a backend with itself")
    higher_better = metric == "accuracy"
    policy = policy or DecisionPolicy()

    pairs_a, spec = _evaluate(gate, dataset, backend_a, policy, max_items)
    pairs_b, _ = _evaluate(gate, dataset, backend_b, policy, max_items)
    scores_a = _per_item_scores(pairs_a, spec, metric)
    scores_b = _per_item_scores(pairs_b, spec, metric)
    joint = [(a, b) for a, b in zip(scores_a, scores_b, strict=True)
             if a is not None and b is not None]
    if len(joint) < 2:
        raise EvalError(
            f"paired comparison needs 2+ jointly scored items, got "
            f"{len(joint)}"
        )
    ja = [a for a, _ in joint]
    jb = [b for _, b in joint]
    estimate_a = sum(ja) / len(ja)
    estimate_b = sum(jb) / len(jb)
    diffs = [a - b for a, b in joint]
    mean_diff = sum(diffs) / len(diffs)

    # Bootstrap CI on the paired mean difference.
    diff_ci = bootstrap_mean_ci(
        diffs, n_boot=n_boot, seed=seed,
        metric_name=f"{metric}_diff",
    )
    perm = paired_permutation_test(ja, jb, n_perm=n_perm, seed=seed,
                                   alpha=alpha)
    wins_a = sum(1 for a, b in joint if a > b)
    wins_b = sum(1 for a, b in joint if b > a)
    ties = len(joint) - wins_a - wins_b

    significant = perm.p_value < alpha
    # For lower-better metrics a negative mean_diff favors A.
    a_ahead = (mean_diff > 0.0) == higher_better
    if mean_diff == 0.0:
        verdict = "tie"
    elif significant and a_ahead:
        verdict = "a_better"
    elif significant:
        verdict = "b_better"
    else:
        verdict = "inconclusive"
    return BackendComparison(
        backend_a=backend_a,
        backend_b=backend_b,
        metric=metric,
        higher_better=higher_better,
        n_items=len(pairs_a),
        n_joint=len(joint),
        estimate_a=estimate_a,
        estimate_b=estimate_b,
        mean_diff=mean_diff,
        diff_ci_low=diff_ci.ci_low,
        diff_ci_high=diff_ci.ci_high,
        p_value=perm.p_value,
        alpha=alpha,
        wins_a=wins_a,
        wins_b=wins_b,
        ties=ties,
        verdict=verdict,
    )
