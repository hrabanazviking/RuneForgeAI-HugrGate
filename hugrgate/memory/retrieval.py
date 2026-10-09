"""Decision retrieval. Slice 306.

Recall turns similarity into *advice*: :func:`retrieve` scores past
episodes against current context with a transparent three-part score
— similarity, recency, outcome — and returns ranked
:class:`RetrievalResult` objects that explain their own scores.
:func:`recall` is the one-call convenience: hand it the current
decision's attributes, get back the most relevant precedents.

The recency term uses :mod:`hugrgate.memory.decay`.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.memory.decay import decay_weight
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.similarity import (
    featurize_query,
    most_similar,
)
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "RetrievalResult",
    "recall",
    "retrieve",
]


def _outcome_bonus(episode: EpisodeLike) -> float:
    outcome = episode.outcome
    if outcome is None:
        return 0.5  # unknown: neutral
    return 1.0 if outcome.is_positive() else 0.0


@dataclass(frozen=True)
class RetrievalResult:
    """One recalled precedent with its transparent score breakdown."""

    episode: EpisodeLike
    score: float
    similarity: float
    recency: float
    outcome_bonus: float

    def explain(self) -> str:
        """One-line human-readable account of the score."""
        record = self.episode.record
        return (
            f"score={self.score:.3f} "
            f"(similarity={self.similarity:.3f}, "
            f"recency={self.recency:.3f}, "
            f"outcome_bonus={self.outcome_bonus:.3f}) "
            f"backend={record.backend} model={record.model} "
            f"p={record.probability:.2f} "
            f"episode={self.episode.episode_id[:8]}"
        )


def retrieve(history: HistoryLike, query_features: dict[str, float], *,
             k: int = 5,
             alpha: float = 0.6,
             beta: float = 0.3,
             gamma: float = 0.1,
             half_life_seconds: float = 86400.0,
             min_score: float = 0.0,
             exclude_ids: set[str] | frozenset[str] = frozenset(),
             episodes: Sequence[EpisodeLike] | None = None,
             now: float | None = None) -> list[RetrievalResult]:
    """Recall the top-``k`` precedents for ``query_features``.

    ``score = alpha*similarity + beta*recency + gamma*outcome_bonus``.
    Weights must be non-negative with a positive sum; ``min_score``
    filters weak hits. ``episodes`` scores a caller-supplied subset
    instead of scanning the whole history (used by conditioned
    retrieval); ``now`` is injectable for deterministic tests.
    """
    weights = {"alpha": alpha, "beta": beta, "gamma": gamma}
    for name, value in weights.items():
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")
    if sum(weights.values()) <= 0:
        raise ValueError("at least one of alpha/beta/gamma must be > 0")
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if not 0.0 <= min_score <= 1.0:
        raise ValueError(f"min_score must be in [0, 1], got {min_score}")
    current = time.time() if now is None else now

    if episodes is None:
        episodes = history.find(MemoryQuery())
    # Over-fetch candidates: recency/outcome can promote beyond the
    # pure-similarity top-k.
    candidates = most_similar(query_features, episodes,
                              k=max(k * 4, k + 10),
                              exclude_ids=exclude_ids)
    results = []
    for hit in candidates:
        recency = decay_weight(
            current - hit.episode.recorded_at, half_life_seconds)
        bonus = _outcome_bonus(hit.episode)
        score = (alpha * hit.score + beta * recency + gamma * bonus)
        if score >= min_score:
            results.append(RetrievalResult(
                episode=hit.episode, score=score, similarity=hit.score,
                recency=recency, outcome_bonus=bonus))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:k]


def recall(history: HistoryLike, *, k: int = 5,
           spec: dict[str, Any] | None = None,
           backend: str | None = None,
           model: str | None = None,
           probability: float | None = None,
           accepted: bool | None = None,
           state_keys: list[str] | tuple[str, ...] | None = None,
           domain: str | None = None,
           **retrieve_kwargs: Any) -> list[RetrievalResult]:
    """Build query features from decision attributes and :func:`retrieve`."""
    features = featurize_query(
        spec=spec, backend=backend, model=model, probability=probability,
        accepted=accepted, state_keys=state_keys, domain=domain)
    return retrieve(history, features, k=k, **retrieve_kwargs)
