"""Decision history API. Slice 301.

The campaign's foundation: an :class:`Episode` is one remembered
decision — a deep-copied :class:`~hugrgate.provenance.DecisionRecord`
plus the annotations the memory layer needs (privacy class, tags,
outcome, ground truth). :class:`DecisionHistory` is the append-mostly,
thread-safe, bounded store of episodes.

Design notes (Yrsa Execution Law, rule 8):

- Episodes *snapshot* provenance records instead of indexing into the
  :class:`~hugrgate.provenance.ProvenanceStore`. Index-based references
  break when the provenance store evicts or purges (its
  :meth:`~hugrgate.provenance.ProvenanceStore.purge` re-chains
  survivors), while a snapshot stays valid forever. The duplication
  cost is bounded by ``max_episodes`` and measured by
  :meth:`DecisionHistory.estimate_bytes` (slice 316 hardens this into
  quotas — the Campaign XII finding of +1.3 GB RSS over 1M decisions
  is addressed there).
- The provenance ``record_hash`` is carried inside the snapshot, so a
  memory episode can always be audited back to the tamper-evident
  chain.
- ``import_from_provenance`` lets an existing deployment adopt memory
  without re-running decisions.
"""

from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hugrgate.errors import MemoryError
from hugrgate.privacy import PRIVACY_CLASS_ORDER
from hugrgate.provenance import DecisionRecord, ProvenanceStore

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime cycle
    from hugrgate.memory.groundtruth import GroundTruth
    from hugrgate.memory.outcomes import Outcome

__all__ = [
    "DecisionHistory",
    "Episode",
]


def _check_privacy_class(privacy_class: str) -> str:
    if privacy_class not in PRIVACY_CLASS_ORDER:
        raise ValueError(
            f"unknown privacy_class: {privacy_class!r}; expected one of "
            f"{list(PRIVACY_CLASS_ORDER)}")
    return privacy_class


@dataclass
class Episode:
    """One remembered decision.

    ``record`` is a deep-copied snapshot of the provenance record, so
    later mutation of the caller's objects cannot rewrite history.
    ``outcome`` / ``ground_truth`` are attached by slices 303/304 and
    start as ``None``.
    """

    episode_id: str
    record: DecisionRecord
    recorded_at: float = field(default_factory=time.time)
    privacy_class: str = "standard"
    tags: tuple[str, ...] = ()
    outcome: Outcome | None = None
    ground_truth: GroundTruth | None = None
    annotations: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _check_privacy_class(self.privacy_class)
        if not isinstance(self.record, DecisionRecord):
            raise TypeError(
                "Episode.record must be a DecisionRecord, got "
                f"{type(self.record).__name__}")
        self.tags = tuple(self.tags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "record": self.record.to_dict(),
            "recorded_at": self.recorded_at,
            "privacy_class": self.privacy_class,
            "tags": list(self.tags),
            "outcome": (self.outcome.to_dict() if self.outcome is not None
                        else None),
            "ground_truth": (self.ground_truth.to_dict()
                             if self.ground_truth is not None else None),
            "annotations": dict(self.annotations),
        }


class DecisionHistory:
    """Append-mostly, thread-safe store of decision episodes.

    Parameters
    ----------
    max_episodes:
        Hard bound on retained episodes. When exceeded, the oldest
        episodes are evicted (oldest-first) and
        :meth:`evicted_count` grows. ``None`` means unbounded — the
        operator then owns the memory risk (slice 316 adds quotas).
    """

    def __init__(self, max_episodes: int | None = None) -> None:
        if max_episodes is not None and max_episodes < 1:
            raise ValueError("max_episodes must be >= 1")
        self._max_episodes = max_episodes
        self._episodes: list[Episode] = []
        self._by_id: dict[str, Episode] = {}
        self._evicted = 0
        self._lock = threading.RLock()

    # -- recording ----------------------------------------------------

    def record(self, record: DecisionRecord, *,
               privacy_class: str = "standard",
               tags: tuple[str, ...] | list[str] = ()) -> Episode:
        """Remember one decision; return the stored episode (a copy)."""
        if not isinstance(record, DecisionRecord):
            raise TypeError(
                f"DecisionHistory only records DecisionRecord, got "
                f"{type(record).__name__}")
        _check_privacy_class(privacy_class)
        episode = Episode(
            episode_id=uuid.uuid4().hex,
            record=copy.deepcopy(record),
            privacy_class=privacy_class,
            tags=tuple(tags),
        )
        with self._lock:
            self._episodes.append(episode)
            self._by_id[episode.episode_id] = episode
            while (self._max_episodes is not None
                   and len(self._episodes) > self._max_episodes):
                dropped = self._episodes.pop(0)
                del self._by_id[dropped.episode_id]
                self._evicted += 1
        return copy.deepcopy(episode)

    def import_from_provenance(
            self, store: ProvenanceStore, *,
            privacy_class: str = "standard") -> int:
        """Snapshot every record in ``store`` as a new episode.

        Returns the number of episodes created. Existing episodes are
        kept; this is additive, never destructive.
        """
        if not isinstance(store, ProvenanceStore):
            raise TypeError(
                f"import_from_provenance needs a ProvenanceStore, got "
                f"{type(store).__name__}")
        _check_privacy_class(privacy_class)
        records = store.recent(store.count())
        for record in records:
            self.record(record, privacy_class=privacy_class)
        return len(records)

    # -- reading ------------------------------------------------------

    def get(self, episode_id: str) -> Episode:
        """Return a copy of one episode; raise MemoryError if unknown."""
        with self._lock:
            episode = self._by_id.get(episode_id)
            if episode is None:
                raise MemoryError(
                    f"unknown episode_id: {episode_id!r}",
                    episode_id=episode_id)
            return copy.deepcopy(episode)

    def recent(self, n: int = 10) -> list[Episode]:
        """Newest-first? No — chronological, newest last, like provenance."""
        if n < 0:
            raise ValueError(f"recent(n) needs n >= 0, got {n}")
        if n == 0:
            return []
        with self._lock:
            return copy.deepcopy(self._episodes[-n:])

    def count(self) -> int:
        with self._lock:
            return len(self._episodes)

    def evicted_count(self) -> int:
        with self._lock:
            return self._evicted

    def by_request_hash(self, request_hash: str) -> list[Episode]:
        """All episodes whose record matches a provenance request hash."""
        with self._lock:
            return copy.deepcopy(
                [e for e in self._episodes
                 if e.record.request_hash == request_hash])

    def episodes_between(self, start: float, end: float) -> list[Episode]:
        """Episodes with ``start <= recorded_at <= end`` (epoch seconds)."""
        if end < start:
            raise ValueError(
                f"episodes_between needs start <= end, got {start} > {end}")
        with self._lock:
            return copy.deepcopy(
                [e for e in self._episodes
                 if start <= e.recorded_at <= end])

    def clear(self) -> int:
        """Remove all episodes; return how many were removed."""
        with self._lock:
            removed = len(self._episodes)
            self._episodes.clear()
            self._by_id.clear()
            return removed

    # -- introspection -------------------------------------------------

    def estimate_bytes(self) -> int:
        """Rough in-memory footprint of the retained episodes.

        Canonical JSON length of each episode plus a fixed per-episode
        overhead for Python object headers. Approximate — a budgeting
        aid for slice 316 quotas, not an allocator reading.
        """
        with self._lock:
            episodes = list(self._episodes)
        total = 0
        for episode in episodes:
            body = json.dumps(episode.to_dict(), sort_keys=True,
                              default=str)
            total += len(body.encode("utf-8")) + 512
        return total
