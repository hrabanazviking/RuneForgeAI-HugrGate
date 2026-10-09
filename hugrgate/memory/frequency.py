"""Frequency features. Slice 310.

"How often has this happened?" Raw and decay-weighted counts grouped
by caller-chosen keys (backend, model, backend+value, outcome kind,
...). :func:`count_by` scans at most ``limit`` episodes newest-first
and returns a :class:`FrequencyTable` mapping each key to its
:class:`FrequencyEntry` (raw count, decay-weighted count, first/last
seen timestamps, per-outcome-kind breakdown).

Decay-weighted counts answer "how often *lately*"; raw counts answer
"how often *ever*". Both are reported — the consumer decides which
to trust.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.decay import decay_weight
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "FrequencyEntry",
    "FrequencyTable",
    "by_backend",
    "by_backend_value",
    "by_model",
    "by_outcome_kind",
    "count_by",
]

#: Key function: episode -> group key string.
KeyFn = Callable[[EpisodeLike], str]


def by_backend(episode: EpisodeLike) -> str:
    """Group by serving backend."""
    return episode.record.backend


def by_model(episode: EpisodeLike) -> str:
    """Group by backend + model."""
    return f"{episode.record.backend}/{episode.record.model}"


def by_backend_value(episode: EpisodeLike) -> str:
    """Group by backend + decided value (values are stringified)."""
    return f"{episode.record.backend}={episode.record.value!r}"


def by_outcome_kind(episode: EpisodeLike) -> str:
    """Group by observed outcome kind ('unknown' when not attached)."""
    outcome = episode.outcome
    return outcome.kind if outcome is not None else "unknown"


@dataclass
class FrequencyEntry:
    """Counts for one group key."""

    key: str
    count: int
    decayed_count: float
    first_seen: float
    last_seen: float
    outcome_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "count": self.count,
            "decayed_count": self.decayed_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "outcome_counts": dict(self.outcome_counts),
        }


@dataclass
class FrequencyTable:
    """Result of :func:`count_by`: entries keyed by group key."""

    entries: dict[str, FrequencyEntry]
    total: int
    decayed_total: float

    def top(self, n: int = 5) -> list[FrequencyEntry]:
        """Top-``n`` entries by decayed count (ties: raw count)."""
        if n < 0:
            raise ValueError(f"n must be >= 0, got {n}")
        ranked = sorted(self.entries.values(),
                        key=lambda e: (e.decayed_count, e.count),
                        reverse=True)
        return ranked[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
            "total": self.total,
            "decayed_total": self.decayed_total,
        }


def count_by(history: HistoryLike, key_fn: KeyFn, *,
             half_life_seconds: float = 86400.0,
             limit: int = 5000,
             query: MemoryQuery | None = None,
             now: float | None = None) -> FrequencyTable:
    """Count episodes grouped by ``key_fn`` (raw + decay-weighted).

    Scans at most ``limit`` episodes newest-first; an optional
    :class:`MemoryQuery` pre-filters. ``now`` is injectable for
    deterministic tests.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    current = time.time() if now is None else now
    episodes: Sequence[EpisodeLike] = history.find(
        query if query is not None else MemoryQuery())
    # newest first, then cap
    ordered = sorted(episodes, key=lambda e: e.recorded_at, reverse=True)
    ordered = ordered[:limit]

    entries: dict[str, FrequencyEntry] = {}
    for episode in ordered:
        key = key_fn(episode)
        if not isinstance(key, str) or not key:
            raise ValueError(
                f"key function must return a non-empty string, got "
                f"{key!r}")
        weight = decay_weight(current - episode.recorded_at,
                              half_life_seconds)
        entry = entries.get(key)
        outcome = episode.outcome
        if entry is None:
            entry = FrequencyEntry(
                key=key, count=0, decayed_count=0.0,
                first_seen=episode.recorded_at,
                last_seen=episode.recorded_at)
            entries[key] = entry
        entry.count += 1
        entry.decayed_count += weight
        entry.first_seen = min(entry.first_seen, episode.recorded_at)
        entry.last_seen = max(entry.last_seen, episode.recorded_at)
        if outcome is not None:
            entry.outcome_counts[outcome.kind] = \
                entry.outcome_counts.get(outcome.kind, 0) + 1
    total = sum(e.count for e in entries.values())
    decayed_total = sum(e.decayed_count for e in entries.values())
    return FrequencyTable(entries=entries, total=total,
                          decayed_total=decayed_total)
