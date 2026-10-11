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
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import MemoryError
from hugrgate.memory.compaction import CompactionSummary
from hugrgate.memory.groundtruth import GroundTruth
from hugrgate.memory.outcomes import Outcome
from hugrgate.memory.policies import MemoryDecision, MemoryPolicy
from hugrgate.memory.query import MemoryQuery
from hugrgate.privacy import PRIVACY_CLASS_ORDER
from hugrgate.provenance import DecisionRecord, ProvenanceStore

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

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Episode:
        """Rebuild from :meth:`to_dict`.

        Raises ``ValueError`` on malformed envelopes and
        :class:`SpecError` when the embedded record is malformed.
        """
        if not isinstance(d, Mapping):
            raise ValueError(
                f"Episode.from_dict needs a mapping, got "
                f"{type(d).__name__}")
        try:
            episode_id = d["episode_id"]
            record_d = d["record"]
        except KeyError as exc:
            raise ValueError(
                f"Episode.from_dict missing key: {exc}") from exc
        record = DecisionRecord.from_dict(record_d)
        outcome_d = d.get("outcome")
        truth_d = d.get("ground_truth")
        return cls(
            episode_id=episode_id,
            record=record,
            recorded_at=d.get("recorded_at") or time.time(),
            privacy_class=d.get("privacy_class", "standard"),
            tags=tuple(d.get("tags") or ()),
            outcome=(Outcome.from_dict(outcome_d)
                     if outcome_d is not None else None),
            ground_truth=(GroundTruth.from_dict(truth_d)
                          if truth_d is not None else None),
            annotations=dict(d.get("annotations") or {}),
        )


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
        self._summaries: list[CompactionSummary] = []
        self._evicted = 0
        self._lock = threading.RLock()

    # -- recording ----------------------------------------------------

    def record(self, record: DecisionRecord, *,
               privacy_class: str = "standard",
               tags: tuple[str, ...] | list[str] = (),
               policy: MemoryPolicy | None = None) -> Episode | None:
        """Remember one decision; return the stored episode (a copy).

        When ``policy`` is given, its verdict applies first: a
        ``"drop"`` verdict skips recording and returns ``None``; a
        ``"redact"`` verdict strips the record's metadata before the
        episode is stored (marked in ``annotations``).
        """
        if not isinstance(record, DecisionRecord):
            raise TypeError(
                f"DecisionHistory only records DecisionRecord, got "
                f"{type(record).__name__}")
        _check_privacy_class(privacy_class)
        tags = tuple(tags)
        annotations: dict[str, Any] = {}
        if policy is not None:
            decision: MemoryDecision = policy.decide(
                record, privacy_class, tags)
            if decision.action == "drop":
                return None
            if decision.action == "redact":
                annotations["redacted"] = True
                annotations["redact_rule"] = decision.rule
        stored_record = copy.deepcopy(record)
        if annotations.get("redacted"):
            stored_record.metadata = {}
        episode = Episode(
            episode_id=uuid.uuid4().hex,
            record=stored_record,
            privacy_class=privacy_class,
            tags=tags,
            annotations=annotations,
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

    def import_episode(self, episode: Episode) -> str:
        """Restore a previously exported episode (slice 318).

        The episode keeps its original ``episode_id``; raises
        :class:`MemoryError` on a duplicate id. Returns the id.
        """
        if not isinstance(episode, Episode):
            raise TypeError(
                f"import_episode needs an Episode, got "
                f"{type(episode).__name__}")
        with self._lock:
            if episode.episode_id in self._by_id:
                raise MemoryError(
                    f"duplicate episode_id on import: "
                    f"{episode.episode_id!r}",
                    episode_id=episode.episode_id)
            stored = copy.deepcopy(episode)
            self._episodes.append(stored)
            self._by_id[stored.episode_id] = stored
            return stored.episode_id

    def clear(self) -> int:
        """Remove all episodes; return how many were removed."""
        with self._lock:
            removed = len(self._episodes)
            self._episodes.clear()
            self._by_id.clear()
            return removed

    def purge(self, predicate) -> int:
        """Remove episodes matching ``predicate``; return the count.

        Slice 316: the retention primitive. ``predicate`` receives an
        episode and returns truthy to remove it. Thread-safe.
        """
        with self._lock:
            kept = [e for e in self._episodes if not predicate(e)]
            removed = len(self._episodes) - len(kept)
            if removed:
                self._episodes = kept
                self._by_id = {e.episode_id: e for e in kept}
            return removed

    def add_compaction_summary(self, summary: CompactionSummary) -> None:
        """Store a compaction summary (slice 317)."""
        if not isinstance(summary, CompactionSummary):
            raise TypeError(
                f"add_compaction_summary needs a CompactionSummary, got "
                f"{type(summary).__name__}")
        with self._lock:
            self._summaries.append(summary)

    def compaction_summaries(self) -> list[CompactionSummary]:
        """Copies of stored compaction summaries, oldest first."""
        with self._lock:
            return copy.deepcopy(self._summaries)

    def find(self, query: MemoryQuery, *,
             limit: int | None = None, offset: int = 0) -> list[Episode]:
        """Run a :class:`MemoryQuery`; return deep copies, never aliases.

        Slice 16: ``limit``/``offset`` paginate the query's matched,
        sorted result (after any pagination in ``query`` itself).
        Defaults (``limit=None``, ``offset=0``) return the query's full
        result, exactly as before.
        """
        if not isinstance(query, MemoryQuery):
            raise TypeError(
                f"find needs a MemoryQuery, got {type(query).__name__}")
        if limit is not None and limit < 0:
            raise ValueError(f"limit must be >= 0, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be >= 0, got {offset}")
        with self._lock:
            snapshot = copy.deepcopy(self._episodes)
        matched = query.apply(snapshot)
        if limit is None and offset == 0:
            return matched
        end = None if limit is None else offset + limit
        return matched[offset:end]

    def attach_outcome(self, episode_id: str, outcome: Outcome, *,
                       overwrite: bool = False) -> Episode:
        """Record what actually happened for one episode (slice 303).

        Raises :class:`MemoryError` for an unknown id, or when an
        outcome is already attached and ``overwrite`` is False.
        Returns a copy of the updated episode.
        """
        if not isinstance(outcome, Outcome):
            raise TypeError(
                f"attach_outcome needs an Outcome, got "
                f"{type(outcome).__name__}")
        with self._lock:
            episode = self._by_id.get(episode_id)
            if episode is None:
                raise MemoryError(
                    f"unknown episode_id: {episode_id!r}",
                    episode_id=episode_id)
            if episode.outcome is not None and not overwrite:
                raise MemoryError(
                    f"episode {episode_id!r} already has an outcome; "
                    f"pass overwrite=True to replace it",
                    episode_id=episode_id)
            episode.outcome = outcome
            return copy.deepcopy(episode)

    def attach_ground_truth(self, episode_id: str, truth: GroundTruth, *,
                            supersede: bool = False) -> Episode:
        """Attach a verified label to one episode (slice 304).

        Ground truth is immutable once set: re-attaching requires
        ``supersede=True``, and the displaced truth is preserved in
        ``episode.annotations["ground_truth_revisions"]`` so corrections
        stay auditable. Raises :class:`MemoryError` for an unknown id
        or a non-superseding re-attach. Returns a copy of the updated
        episode.
        """
        if not isinstance(truth, GroundTruth):
            raise TypeError(
                f"attach_ground_truth needs a GroundTruth, got "
                f"{type(truth).__name__}")
        with self._lock:
            episode = self._by_id.get(episode_id)
            if episode is None:
                raise MemoryError(
                    f"unknown episode_id: {episode_id!r}",
                    episode_id=episode_id)
            if episode.ground_truth is not None and not supersede:
                raise MemoryError(
                    f"episode {episode_id!r} already has ground truth; "
                    f"pass supersede=True to correct it",
                    episode_id=episode_id)
            if episode.ground_truth is not None:
                revisions = episode.annotations.setdefault(
                    "ground_truth_revisions", [])
                revisions.append(episode.ground_truth.to_dict())
            episode.ground_truth = truth
            return copy.deepcopy(episode)

    def consistency_report(self) -> list[dict[str, Any]]:
        """Episodes where ground truth contradicts the attached outcome.

        Each entry carries ``episode_id``, the outcome kind, the truth
        label, and the truth source — the audit trail a reviewer needs.
        Episodes without both attachments, or with non-comparable
        labels, are skipped.
        """
        from hugrgate.memory.groundtruth import outcome_agrees
        report = []
        episodes = self.find(MemoryQuery(has_outcome=True,
                                         has_ground_truth=True))
        for episode in episodes:
            outcome = episode.outcome
            truth = episode.ground_truth
            if outcome is None or truth is None:
                continue
            if outcome_agrees(truth, outcome) is False:
                report.append({
                    "episode_id": episode.episode_id,
                    "outcome_kind": outcome.kind,
                    "truth_label": truth.label,
                    "truth_source": truth.source,
                })
        return report

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
