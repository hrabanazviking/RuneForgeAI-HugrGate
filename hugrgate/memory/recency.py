"""Recency features. Slice 309.

Raw timestamps are hard for downstream consumers to use; this module
distills "how recently did something like this happen, and how did it
go?" into a typed feature vector:

- ``time_since_last_similar`` — seconds since the most recent episode
  above the similarity threshold (``None`` when nothing is similar);
- ``last_outcome_kind`` — the outcome kind of that episode;
- ``success_streak`` / ``failure_streak`` — the current consecutive
  run of positive / negative outcomes among similar episodes ordered
  newest-first (a streak is a property of the *head* of history);
- ``similar_count`` / ``effective_similar_count`` — raw and
  decay-weighted counts of similar episodes;
- ``mean_similarity`` — average cosine of the similar set.

"Similar" means cosine >= ``similarity_threshold`` against the query
features. At most ``max_candidates`` episodes are scanned, newest
first — recency features must stay cheap on large histories.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from hugrgate.memory.decay import decay_weight
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.similarity import cosine, featurize_episode
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "RecencyFeatures",
    "recency_features",
]


@dataclass(frozen=True)
class RecencyFeatures:
    """Distilled recency signals for one query context."""

    time_since_last_similar: float | None
    last_outcome_kind: str | None
    success_streak: int
    failure_streak: int
    similar_count: int
    effective_similar_count: float
    mean_similarity: float

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "time_since_last_similar": self.time_since_last_similar,
            "last_outcome_kind": self.last_outcome_kind,
            "success_streak": self.success_streak,
            "failure_streak": self.failure_streak,
            "similar_count": self.similar_count,
            "effective_similar_count": self.effective_similar_count,
            "mean_similarity": self.mean_similarity,
        }


def recency_features(history: HistoryLike,
                     query_features: dict[str, float], *,
                     similarity_threshold: float = 0.5,
                     half_life_seconds: float = 86400.0,
                     max_candidates: int = 500,
                     now: float | None = None) -> RecencyFeatures:
    """Compute recency features of similar episodes in ``history``."""
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError(
            f"similarity_threshold must be in [0, 1], got "
            f"{similarity_threshold}")
    if max_candidates < 1:
        raise ValueError(
            f"max_candidates must be >= 1, got {max_candidates}")
    current = time.time() if now is None else now

    episodes = history.find(MemoryQuery())
    scored: list[tuple[float, EpisodeLike]] = []
    for episode in episodes:
        score = cosine(query_features, featurize_episode(episode))
        if score >= similarity_threshold:
            scored.append((score, episode))
    # newest first; cap the scan for large histories
    scored.sort(key=lambda item: item[1].recorded_at, reverse=True)
    scored = scored[:max_candidates]

    if not scored:
        return RecencyFeatures(
            time_since_last_similar=None,
            last_outcome_kind=None,
            success_streak=0,
            failure_streak=0,
            similar_count=0,
            effective_similar_count=0.0,
            mean_similarity=0.0,
        )

    newest = scored[0][1]
    last_outcome = newest.outcome
    success_streak = 0
    failure_streak = 0
    for _, episode in scored:
        outcome = episode.outcome
        if outcome is None:
            break
        if outcome.is_positive():
            if failure_streak:
                break
            success_streak += 1
        else:
            if success_streak:
                break
            failure_streak += 1

    ages = [current - episode.recorded_at for _, episode in scored]
    return RecencyFeatures(
        time_since_last_similar=max(0.0, ages[0]),
        last_outcome_kind=(last_outcome.kind if last_outcome else None),
        success_streak=success_streak,
        failure_streak=failure_streak,
        similar_count=len(scored),
        effective_similar_count=sum(
            decay_weight(age, half_life_seconds) for age in ages),
        mean_similarity=sum(s for s, _ in scored) / len(scored),
    )
