"""Memory compaction. Slice 317.

Retention (slice 316) deletes; compaction *summarizes*. Old episodes
are rolled up into :class:`CompactionSummary` aggregates — per-backend
counts, outcome distribution, success rate, mean probability, privacy
class mix — and the raw episodes are purged. The summary stays on the
history (``compaction_summaries()``), so the past remains queryable as
statistics even after its details are gone.

Episodes carrying ground truth are kept by default: verified labels
are the scarcest asset in the store, and aggregates cannot replace
them. Pass ``keep_with_ground_truth=False`` to compact those too.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import HistoryLike

__all__ = [
    "CompactionSummary",
    "compact",
]


@dataclass(frozen=True)
class CompactionSummary:
    """Aggregate left behind after compacting old episodes."""

    window_start: float
    window_end: float
    episode_count: int
    backend_counts: dict[str, int] = field(default_factory=dict)
    outcome_counts: dict[str, int] = field(default_factory=dict)
    success_rate: float | None = None
    mean_probability: float | None = None
    privacy_class_counts: dict[str, int] = field(default_factory=dict)
    compacted_episode_ids: tuple[str, ...] = ()
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "episode_count": self.episode_count,
            "backend_counts": dict(self.backend_counts),
            "outcome_counts": dict(self.outcome_counts),
            "success_rate": self.success_rate,
            "mean_probability": self.mean_probability,
            "privacy_class_counts": dict(self.privacy_class_counts),
            "compacted_episode_ids": list(self.compacted_episode_ids),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> CompactionSummary:
        """Rebuild from :meth:`to_dict`; ``ValueError`` on bad data."""
        if not isinstance(d, Mapping):
            raise ValueError("CompactionSummary.from_dict needs a mapping")
        try:
            window_start = d["window_start"]
            window_end = d["window_end"]
            episode_count = d["episode_count"]
        except KeyError as exc:
            raise ValueError(
                f"CompactionSummary.from_dict missing key: {exc}") from exc
        return cls(
            window_start=window_start,
            window_end=window_end,
            episode_count=episode_count,
            backend_counts=dict(d.get("backend_counts") or {}),
            outcome_counts=dict(d.get("outcome_counts") or {}),
            success_rate=d.get("success_rate"),
            mean_probability=d.get("mean_probability"),
            privacy_class_counts=dict(d.get("privacy_class_counts") or {}),
            compacted_episode_ids=tuple(d.get("compacted_episode_ids") or ()),
            created_at=d.get("created_at") or 0.0,
        )


def compact(history: HistoryLike, *, older_than_seconds: float,
            keep_with_ground_truth: bool = True,
            now: float | None = None) -> CompactionSummary | None:
    """Compact episodes older than ``older_than_seconds``.

    Returns the summary, or ``None`` when nothing was old enough.
    The summary is stored on the history via
    ``add_compaction_summary`` when the history supports it
    (:class:`DecisionHistory` does).
    """
    if older_than_seconds <= 0:
        raise ValueError(
            f"older_than_seconds must be > 0, got {older_than_seconds}")
    current = time.time() if now is None else now
    cutoff = current - older_than_seconds

    candidates = [e for e in history.find(MemoryQuery())
                  if e.recorded_at < cutoff]
    if keep_with_ground_truth:
        candidates = [e for e in candidates if e.ground_truth is None]
    if not candidates:
        return None

    backend_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    privacy_counts: Counter[str] = Counter()
    positive = 0
    labeled = 0
    probabilities: list[float] = []
    for episode in candidates:
        backend_counts[episode.record.backend] += 1
        privacy_counts[episode.privacy_class] += 1
        probabilities.append(episode.record.probability)
        outcome = episode.outcome
        if outcome is not None:
            labeled += 1
            outcome_counts[outcome.kind] += 1
            if outcome.is_positive():
                positive += 1

    summary = CompactionSummary(
        window_start=min(e.recorded_at for e in candidates),
        window_end=max(e.recorded_at for e in candidates),
        episode_count=len(candidates),
        backend_counts=dict(backend_counts),
        outcome_counts=dict(outcome_counts),
        success_rate=(positive / labeled if labeled else None),
        mean_probability=(sum(probabilities) / len(probabilities)
                          if probabilities else None),
        privacy_class_counts=dict(privacy_counts),
        compacted_episode_ids=tuple(e.episode_id for e in candidates),
        created_at=current,
    )
    doomed = set(summary.compacted_episode_ids)
    history.purge(lambda e, doomed=doomed: e.episode_id in doomed)
    add = getattr(history, "add_compaction_summary", None)
    if callable(add):
        add(summary)
    return summary
