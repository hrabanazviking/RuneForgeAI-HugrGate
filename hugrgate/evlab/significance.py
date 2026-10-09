"""Significance testing for paired evaluation outcomes. Slice 359.

When backend A scores 0.83 and B scores 0.81 on the same items, is
that signal or noise?  This module answers with paired,
distribution-free tests over per-item scores — no normality
assumptions, no opaque tables:

- :func:`paired_permutation_test` — the workhorse: randomly flips the
  sign of per-item differences (Monte Carlo, seeded) and counts how
  often the reshuffled mean beats the observed one.  Valid p-values
  via the ``(count + 1) / (n_perm + 1)`` form.
- :func:`mcnemar_test` — for paired binary correctness (A-right/B-
  wrong vs A-wrong/B-right discordant pairs); exact two-sided binomial
  p-value in pure stdlib, plus the chi-square statistic with
  continuity correction for reference.
- :func:`compare_paired_correctness` — lab convenience: takes two
  ``(expected, DecisionResult)`` pair lists, derives per-item
  correctness, and runs both tests.

Effect sizes ride along descriptively (mean difference, Cohen's
``dz``); they are not p-values and are labeled as such.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import EvalError
from hugrgate.result import DecisionResult

__all__ = [
    "SignificanceResult",
    "compare_paired_correctness",
    "mcnemar_test",
    "paired_permutation_test",
]

_MIN_PERM = 1000


@dataclass
class SignificanceResult:
    """One significance test's outcome (slice 359)."""

    test: str
    statistic: float
    p_value: float
    alpha: float
    n: int
    details: dict[str, Any]

    @property
    def significant(self) -> bool:
        return self.p_value < self.alpha

    @property
    def verdict(self) -> str:
        return "significant" if self.significant else "not significant"

    def to_dict(self) -> dict[str, Any]:
        return {
            "test": self.test,
            "statistic": self.statistic,
            "p_value": self.p_value,
            "alpha": self.alpha,
            "n": self.n,
            "significant": self.significant,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignificanceResult:
        return cls(
            test=data["test"],
            statistic=data["statistic"],
            p_value=data["p_value"],
            alpha=data["alpha"],
            n=data["n"],
            details=dict(data.get("details", {})),
        )


def _check_scores(
    scores_a: Sequence[float], scores_b: Sequence[float]
) -> tuple[list[float], list[float]]:
    a = list(scores_a)
    b = list(scores_b)
    if len(a) != len(b):
        raise EvalError(
            f"paired scores must have equal length, got {len(a)} vs {len(b)}"
        )
    if len(a) < 2:
        raise EvalError(
            f"paired tests need at least 2 items, got {len(a)}"
        )
    for seq, name in ((a, "scores_a"), (b, "scores_b")):
        for v in seq:
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise EvalError(
                    f"{name} must contain finite numbers, got {v!r}"
                )
    return [float(v) for v in a], [float(v) for v in b]


def paired_permutation_test(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
    *,
    n_perm: int = 10000,
    seed: int = 0,
    alternative: str = "two-sided",
    alpha: float = 0.05,
) -> SignificanceResult:
    """Paired permutation test on per-item score differences.

    ``alternative``: ``"two-sided"``, ``"greater"`` (A > B), or
    ``"less"`` (A < B).  Deterministic for a fixed seed.
    """
    a, b = _check_scores(scores_a, scores_b)
    if alternative not in ("two-sided", "greater", "less"):
        raise EvalError(
            f"unknown alternative {alternative!r}; expected "
            "'two-sided', 'greater', or 'less'"
        )
    if n_perm < _MIN_PERM:
        raise EvalError(
            f"n_perm must be >= {_MIN_PERM} for a meaningful test, "
            f"got {n_perm}"
        )
    if not 0.0 < alpha < 1.0:
        raise EvalError(f"alpha must be in (0, 1), got {alpha}")

    diffs = [x - y for x, y in zip(a, b, strict=True)]
    observed = sum(diffs) / len(diffs)
    abs_obs = abs(observed)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        flipped = sum(d * (1.0 if rng.random() < 0.5 else -1.0)
                      for d in diffs) / len(diffs)
        if alternative == "two-sided":
            hit = abs(flipped) >= abs_obs
        elif alternative == "greater":
            hit = flipped >= observed
        else:
            hit = flipped <= observed
        if hit:
            extreme += 1
    # Plus-one form: valid (conservative) Monte Carlo p-value.
    p_value = (extreme + 1) / (n_perm + 1)
    mean_diff = observed
    var = sum((d - observed) ** 2 for d in diffs) / len(diffs)
    cohens_dz = observed / math.sqrt(var) if var > 0 else 0.0
    return SignificanceResult(
        test="paired_permutation",
        statistic=observed,
        p_value=p_value,
        alpha=alpha,
        n=len(diffs),
        details={
            "alternative": alternative,
            "n_perm": n_perm,
            "seed": seed,
            "mean_difference": mean_diff,
            "cohens_dz": cohens_dz,
        },
    )


def _binom_cdf_leq(k: int, n: int, p: float = 0.5) -> float:
    """P(X <= k) for Binomial(n, p), pure stdlib."""
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
               for i in range(k + 1))


def mcnemar_test(
    b01: int,
    b10: int,
    *,
    alpha: float = 0.05,
) -> SignificanceResult:
    """McNemar's test on paired binary correctness.

    ``b01``: A wrong / B right; ``b10``: A right / B wrong.  The
    p-value is the exact two-sided binomial test on the discordant
    pairs; the chi-square statistic (continuity-corrected) is reported
    for reference.
    """
    for name, value in (("b01", b01), ("b10", b10)):
        if not isinstance(value, int) or value < 0:
            raise EvalError(f"{name} must be a non-negative int")
    if not 0.0 < alpha < 1.0:
        raise EvalError(f"alpha must be in (0, 1), got {alpha}")
    n = b01 + b10
    if n == 0:
        raise EvalError(
            "McNemar needs at least one discordant pair "
            "(the backends never disagree)"
        )
    k = min(b01, b10)
    # Exact two-sided p: 2 * min(tail), capped at 1.
    p_value = min(1.0, 2.0 * _binom_cdf_leq(k, n))
    chi2 = (abs(b01 - b10) - 1.0) ** 2 / n if n else 0.0
    return SignificanceResult(
        test="mcnemar",
        statistic=chi2,
        p_value=p_value,
        alpha=alpha,
        n=n,
        details={
            "b01": b01,
            "b10": b10,
            "p_value_method": "exact_two_sided_binomial",
        },
    )


def _correct(expected: Any, result: DecisionResult | None) -> int | None:
    if expected is None or result is None or result.value is None:
        return None
    if isinstance(expected, list):
        return 1 if set(result.value or []) == set(expected) else 0
    return 1 if result.value == expected else 0


def compare_paired_correctness(
    pairs_a: Sequence[tuple[Any, DecisionResult | None]],
    pairs_b: Sequence[tuple[Any, DecisionResult | None]],
    *,
    n_perm: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
    label_a: str = "a",
    label_b: str = "b",
) -> dict[str, Any]:
    """Run McNemar + permutation on two backends' paired outcomes.

    Items where either backend abstained (or lacks an expected value)
    are excluded from both tests — the tests are *paired*, so the item
    sets must match exactly.  Returns a JSON-serializable report.
    """
    if len(pairs_a) != len(pairs_b):
        raise EvalError(
            f"paired comparisons need equal item counts, got "
            f"{len(pairs_a)} vs {len(pairs_b)}"
        )
    correct_a: list[int] = []
    correct_b: list[int] = []
    for (exp_a, res_a), (exp_b, res_b) in zip(pairs_a, pairs_b,
                                             strict=True):
        ca = _correct(exp_a, res_a)
        cb = _correct(exp_b, res_b)
        if ca is None or cb is None:
            continue
        correct_a.append(ca)
        correct_b.append(cb)
    if len(correct_a) < 2:
        raise EvalError(
            "paired comparison needs at least 2 jointly scored items, "
            f"got {len(correct_a)}"
        )
    b01 = sum(1 for ca, cb in zip(correct_a, correct_b, strict=True)
              if ca == 0 and cb == 1)
    b10 = sum(1 for ca, cb in zip(correct_a, correct_b, strict=True)
              if ca == 1 and cb == 0)
    mcnemar = mcnemar_test(b01, b10, alpha=alpha)
    perm = paired_permutation_test(
        correct_a, correct_b, n_perm=n_perm, seed=seed, alpha=alpha)
    return {
        "label_a": label_a,
        "label_b": label_b,
        "n_items": len(correct_a),
        "accuracy_a": sum(correct_a) / len(correct_a),
        "accuracy_b": sum(correct_b) / len(correct_b),
        "mcnemar": mcnemar.to_dict(),
        "permutation": perm.to_dict(),
    }
