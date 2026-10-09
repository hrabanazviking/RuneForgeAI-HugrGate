"""Historical counterfactuals. Slice 320.

"What if we had routed these decisions to backend X instead?" Memory
cannot rerun the past, but it can compare what *did* happen in
similar situations per backend or per chosen value — with honest
uncertainty. Every estimate carries a Wilson score interval, and
estimates below ``min_n`` samples are flagged
``sufficient_data=False`` instead of being dressed up.

Stated assumptions (Yrsa Execution Law, rule 12 — never invent what
the data cannot support):

- similar past contexts are exchangeable with the query context
  (cosine >= ``min_similarity`` on auditable features);
- outcome scores are comparable across episodes;
- there is no unmeasured confounding — this is observational
  comparison, not a randomized trial.

For propensity-weighted off-policy evaluation on telemetry with
logged propensities, see
:mod:`hugrgate.adaptive.counterfactual` (IPS/SNIPS/DR estimators);
that module answers a different question from different data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.similarity import cosine, featurize_episode
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "BackendCounterfactual",
    "ValueCounterfactual",
    "counterfactual_backends",
    "counterfactual_value",
    "wilson_interval",
]


def wilson_interval(successes: int, n: int,
                    z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    ``(lo, hi)`` clamped to [0, 1]; ``(0.0, 1.0)`` when ``n == 0``.
    """
    if n < 0 or successes < 0 or successes > n:
        raise ValueError(
            f"need 0 <= successes <= n, got {successes}/{n}")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _similar_episodes(history: HistoryLike,
                      query_features: dict[str, float],
                      min_similarity: float,
                      max_candidates: int) -> list[tuple[float, EpisodeLike]]:
    if not 0.0 <= min_similarity <= 1.0:
        raise ValueError(
            f"min_similarity must be in [0, 1], got {min_similarity}")
    scored = []
    for episode in history.find(MemoryQuery()):
        score = cosine(query_features, featurize_episode(episode))
        if score >= min_similarity:
            scored.append((score, episode))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:max_candidates]


def _summarize(group: list[EpisodeLike]) -> tuple[int, int, float | None,
                                                 tuple[float, float]]:
    """(labeled_n, positives, mean_score_or_None, wilson_interval)."""
    positives = 0
    labeled = 0
    scores: list[float] = []
    for episode in group:
        outcome = episode.outcome
        if outcome is None:
            continue
        labeled += 1
        if outcome.is_positive():
            positives += 1
        if outcome.score is not None:
            scores.append(outcome.score)
    return (labeled, positives,
            sum(scores) / len(scores) if scores else None,
            wilson_interval(positives, labeled))


@dataclass(frozen=True)
class BackendCounterfactual:
    """Observed track record of one backend on similar decisions."""

    backend: str
    n: int
    success_rate: float | None
    wilson_lo: float
    wilson_hi: float
    mean_score: float | None
    sufficient_data: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "n": self.n,
            "success_rate": self.success_rate,
            "wilson_lo": self.wilson_lo,
            "wilson_hi": self.wilson_hi,
            "mean_score": self.mean_score,
            "sufficient_data": self.sufficient_data,
        }


@dataclass(frozen=True)
class ValueCounterfactual:
    """Observed track record of one chosen value on similar decisions."""

    value: Any
    n: int
    success_rate: float | None
    wilson_lo: float
    wilson_hi: float
    sufficient_data: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "n": self.n,
            "success_rate": self.success_rate,
            "wilson_lo": self.wilson_lo,
            "wilson_hi": self.wilson_hi,
            "sufficient_data": self.sufficient_data,
        }


def counterfactual_backends(
    history: HistoryLike,
    query_features: dict[str, float], *,
    min_similarity: float = 0.5,
    min_n: int = 5,
    max_candidates: int = 2000,
) -> list[BackendCounterfactual]:
    """Per-backend success estimates on similar past decisions.

    Sorted by success rate descending (``None`` rates last).
    """
    if min_n < 1:
        raise ValueError(f"min_n must be >= 1, got {min_n}")
    similar = _similar_episodes(history, query_features, min_similarity,
                                max_candidates)
    groups: dict[str, list[EpisodeLike]] = {}
    for _, episode in similar:
        groups.setdefault(episode.record.backend, []).append(episode)
    results = []
    for backend, group in groups.items():
        labeled, positives, mean_score, (lo, hi) = _summarize(group)
        results.append(BackendCounterfactual(
            backend=backend,
            n=labeled,
            success_rate=(positives / labeled if labeled else None),
            wilson_lo=lo,
            wilson_hi=hi,
            mean_score=mean_score,
            sufficient_data=labeled >= min_n,
        ))
    results.sort(key=lambda r: (r.success_rate is not None,
                                r.success_rate or 0.0),
                 reverse=True)
    return results


def counterfactual_value(
    history: HistoryLike,
    query_features: dict[str, float],
    value: Any, *,
    min_similarity: float = 0.5,
    min_n: int = 5,
    max_candidates: int = 2000,
) -> ValueCounterfactual:
    """Success estimate had the decision value been ``value``.

    Compares similar episodes whose recorded value equals ``value``.
    """
    if min_n < 1:
        raise ValueError(f"min_n must be >= 1, got {min_n}")
    similar = _similar_episodes(history, query_features, min_similarity,
                                max_candidates)
    group = [e for _, e in similar if e.record.value == value]
    labeled, positives, _, (lo, hi) = _summarize(group)
    return ValueCounterfactual(
        value=value,
        n=labeled,
        success_rate=(positives / labeled if labeled else None),
        wilson_lo=lo,
        wilson_hi=hi,
        sufficient_data=labeled >= min_n,
    )
