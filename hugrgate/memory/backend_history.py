"""Backend history features. Slice 312.

"What do we know about backend X from history?" One
:class:`BackendHistory` per serving backend: decision counts,
acceptance rate, outcome distribution, success rate among labeled
decisions, probability and latency means (raw and decay-weighted),
first/last seen, and the models observed behind the backend name.

``success_rate`` is ``None`` — not 0 — when no episode carries an
outcome: absence of evidence is not evidence of failure, and slice
322's calibration must not mistake the two.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.decay import decayed_mean
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "BackendHistory",
    "backend_histories",
]


@dataclass(frozen=True)
class BackendHistory:
    """Aggregate track record of one backend."""

    backend: str
    decision_count: int
    accepted_count: int
    accepted_rate: float
    outcome_counts: dict[str, int] = field(default_factory=dict)
    success_rate: float | None = None
    mean_probability: float | None = None
    decayed_mean_probability: float | None = None
    mean_latency_ms: float | None = None
    first_seen: float | None = None
    last_seen: float | None = None
    models: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "decision_count": self.decision_count,
            "accepted_count": self.accepted_count,
            "accepted_rate": self.accepted_rate,
            "outcome_counts": dict(self.outcome_counts),
            "success_rate": self.success_rate,
            "mean_probability": self.mean_probability,
            "decayed_mean_probability": self.decayed_mean_probability,
            "mean_latency_ms": self.mean_latency_ms,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "models": list(self.models),
        }


def backend_histories(history: HistoryLike, *,
                      half_life_seconds: float = 86400.0,
                      limit: int = 5000,
                      query: MemoryQuery | None = None,
                      now: float | None = None
                      ) -> dict[str, BackendHistory]:
    """Aggregate per-backend track records from history."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    current = time.time() if now is None else now
    episodes: Sequence[EpisodeLike] = history.find(
        query if query is not None else MemoryQuery())
    ordered = sorted(episodes, key=lambda e: e.recorded_at, reverse=True)
    ordered = ordered[:limit]

    groups: dict[str, list[EpisodeLike]] = {}
    for episode in ordered:
        groups.setdefault(episode.record.backend, []).append(episode)

    result: dict[str, BackendHistory] = {}
    for backend, group in groups.items():
        accepted = sum(1 for e in group if e.record.accepted)
        outcome_counts: dict[str, int] = {}
        positive = 0
        labeled = 0
        for episode in group:
            outcome = episode.outcome
            if outcome is not None:
                labeled += 1
                outcome_counts[outcome.kind] = \
                    outcome_counts.get(outcome.kind, 0) + 1
                if outcome.is_positive():
                    positive += 1
        probabilities = [e.record.probability for e in group]
        ages = [current - e.recorded_at for e in group]
        latencies = [e.record.latency_ms for e in group
                     if e.record.latency_ms > 0]
        models = sorted({e.record.model for e in group})
        result[backend] = BackendHistory(
            backend=backend,
            decision_count=len(group),
            accepted_count=accepted,
            accepted_rate=accepted / len(group),
            outcome_counts=outcome_counts,
            success_rate=(positive / labeled if labeled else None),
            mean_probability=(sum(probabilities) / len(probabilities)
                              if probabilities else None),
            decayed_mean_probability=decayed_mean(
                probabilities, ages, half_life_seconds),
            mean_latency_ms=(sum(latencies) / len(latencies)
                             if latencies else None),
            first_seen=min(e.recorded_at for e in group),
            last_seen=max(e.recorded_at for e in group),
            models=tuple(models),
        )
    return result
