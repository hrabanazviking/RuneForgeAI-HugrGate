"""Queryable provenance store. Slice 302.

Two complementary surfaces:

1. :class:`MemoryQuery` — a composable, fully typed query object over
   :class:`~hugrgate.memory.history.Episode` objects, executed by
   :meth:`~hugrgate.memory.history.DecisionHistory.find`. Filters,
   sorting, and limit/offset pagination; :meth:`MemoryQuery.explain`
   renders the plan as human-readable text for observability.
2. :func:`find_in_provenance` — the same query language applied to a
   raw :class:`~hugrgate.provenance.ProvenanceStore`, built on the new
   :meth:`~hugrgate.provenance.ProvenanceStore.scan` primitive. Memory-
   only filters (privacy class, tags, outcome, ground truth) are
   rejected explicitly rather than silently ignored.

Queries never mutate the store and always return deep copies.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from hugrgate.errors import MemoryError
from hugrgate.memory.types import EpisodeLike
from hugrgate.provenance import DecisionRecord, ProvenanceStore

__all__ = [
    "MemoryQuery",
    "find_in_provenance",
]

#: Fields a query may sort by.
SORT_FIELDS = ("recorded_at", "probability", "latency_ms")

#: Memory-only filters unavailable on raw provenance records.
_MEMORY_ONLY_FIELDS = (
    "privacy_classes",
    "tags_any",
    "tags_all",
    "outcome_kinds",
    "has_outcome",
    "has_ground_truth",
)

_E = TypeVar("_E", bound=EpisodeLike)


def _frozen(values: Collection[str] | None) -> frozenset[str] | None:
    if values is None:
        return None
    return frozenset(values)


@dataclass
class MemoryQuery:
    """A typed, composable filter over remembered decisions.

    Every filter is optional; an empty query matches everything.
    """

    backends: Collection[str] | None = None
    models: Collection[str] | None = None
    accepted: bool | None = None
    fallback_used: bool | None = None
    recorded_after: float | None = None
    recorded_before: float | None = None
    privacy_classes: Collection[str] | None = None
    tags_any: Collection[str] | None = None
    tags_all: Collection[str] | None = None
    outcome_kinds: Collection[str] | None = None
    has_outcome: bool | None = None
    has_ground_truth: bool | None = None
    min_probability: float | None = None
    max_probability: float | None = None
    request_hashes: Collection[str] | None = None
    sort_by: str = "recorded_at"
    descending: bool = True
    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        self.backends = _frozen(self.backends)
        self.models = _frozen(self.models)
        self.privacy_classes = _frozen(self.privacy_classes)
        self.tags_any = _frozen(self.tags_any)
        self.tags_all = _frozen(self.tags_all)
        self.outcome_kinds = _frozen(self.outcome_kinds)
        self.request_hashes = _frozen(self.request_hashes)
        if self.sort_by not in SORT_FIELDS:
            raise ValueError(
                f"sort_by must be one of {SORT_FIELDS}, got "
                f"{self.sort_by!r}")
        if self.limit is not None and self.limit < 0:
            raise ValueError(f"limit must be >= 0, got {self.limit}")
        if self.offset < 0:
            raise ValueError(f"offset must be >= 0, got {self.offset}")
        for name in ("min_probability", "max_probability"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        if (self.min_probability is not None
                and self.max_probability is not None
                and self.min_probability > self.max_probability):
            raise ValueError("min_probability must be <= max_probability")
        if (self.recorded_after is not None
                and self.recorded_before is not None
                and self.recorded_after > self.recorded_before):
            raise ValueError("recorded_after must be <= recorded_before")

    # -- matching -----------------------------------------------------

    def matches(self, episode: EpisodeLike) -> bool:
        """True when the episode satisfies every set filter."""
        record = episode.record
        if self.backends is not None and record.backend not in self.backends:
            return False
        if self.models is not None and record.model not in self.models:
            return False
        if self.accepted is not None and record.accepted != self.accepted:
            return False
        if (self.fallback_used is not None
                and record.fallback_used != self.fallback_used):
            return False
        if (self.recorded_after is not None
                and episode.recorded_at < self.recorded_after):
            return False
        if (self.recorded_before is not None
                and episode.recorded_at > self.recorded_before):
            return False
        if (self.privacy_classes is not None
                and episode.privacy_class not in self.privacy_classes):
            return False
        tags_any = frozenset(self.tags_any or ())
        if self.tags_any is not None and not (tags_any & set(episode.tags)):
            return False
        tags_all = frozenset(self.tags_all or ())
        if self.tags_all is not None and not tags_all <= set(episode.tags):
            return False
        if self.outcome_kinds is not None:
            if episode.outcome is None or episode.outcome.kind \
                    not in self.outcome_kinds:
                return False
        if self.has_outcome is not None and (
                episode.outcome is not None) != self.has_outcome:
            return False
        if self.has_ground_truth is not None and (
                episode.ground_truth is not None) != self.has_ground_truth:
            return False
        if (self.min_probability is not None
                and record.probability < self.min_probability):
            return False
        if (self.max_probability is not None
                and record.probability > self.max_probability):
            return False
        if (self.request_hashes is not None
                and record.request_hash not in self.request_hashes):
            return False
        return True

    def matches_record(self, record: DecisionRecord) -> bool:
        """Record-level subset of :meth:`matches` (no memory fields)."""
        for name in _MEMORY_ONLY_FIELDS:
            if getattr(self, name) is not None:
                raise MemoryError(
                    f"query filter {name!r} needs episode memory and "
                    f"cannot run on a raw ProvenanceStore",
                    filter=name)
        if self.backends is not None and record.backend not in self.backends:
            return False
        if self.models is not None and record.model not in self.models:
            return False
        if self.accepted is not None and record.accepted != self.accepted:
            return False
        if (self.fallback_used is not None
                and record.fallback_used != self.fallback_used):
            return False
        if (self.recorded_after is not None
                and record.timestamp < self.recorded_after):
            return False
        if (self.recorded_before is not None
                and record.timestamp > self.recorded_before):
            return False
        if (self.min_probability is not None
                and record.probability < self.min_probability):
            return False
        if (self.max_probability is not None
                and record.probability > self.max_probability):
            return False
        if (self.request_hashes is not None
                and record.request_hash not in self.request_hashes):
            return False
        return True

    # -- execution ----------------------------------------------------

    def _sort_key(self, item: Any) -> Any:
        if self.sort_by == "recorded_at":
            # Episodes carry recorded_at; raw records carry timestamp.
            if hasattr(item, "recorded_at"):
                return item.recorded_at
            return item.timestamp
        target = getattr(item, "record", item)
        return getattr(target, self.sort_by)

    def apply(self, episodes: Sequence[_E]) -> list[_E]:
        """Filter, sort, and paginate an episode list (already copies)."""
        matched = [e for e in episodes if self.matches(e)]
        matched.sort(key=self._sort_key, reverse=self.descending)
        start = self.offset
        end = None if self.limit is None else start + self.limit
        return matched[start:end]

    def explain(self) -> str:
        """Human-readable rendering of the query plan."""
        parts = []
        for name in ("backends", "models", "accepted", "fallback_used",
                     "recorded_after", "recorded_before", "privacy_classes",
                     "tags_any", "tags_all", "outcome_kinds", "has_outcome",
                     "has_ground_truth", "min_probability", "max_probability",
                     "request_hashes"):
            value = getattr(self, name)
            if value is not None:
                if isinstance(value, frozenset):
                    value = sorted(value)
                parts.append(f"{name}={value}")
        if not parts and self.sort_by == "recorded_at" \
                and self.descending and self.limit is None \
                and self.offset == 0:
            return "MemoryQuery(match-all)"
        parts.append(f"sort={self.sort_by}:"
                     f"{'desc' if self.descending else 'asc'}")
        if self.limit is not None:
            parts.append(f"limit={self.limit}")
        if self.offset:
            parts.append(f"offset={self.offset}")
        return "MemoryQuery(" + ", ".join(parts) + ")"


def find_in_provenance(store: ProvenanceStore,
                       query: MemoryQuery) -> list[DecisionRecord]:
    """Run ``query`` against a raw :class:`ProvenanceStore`.

    Memory-only filters raise :class:`MemoryError` (see
    :meth:`MemoryQuery.matches_record`). Sorting maps ``recorded_at``
    onto the record timestamp. Results are deep copies.
    """
    if not isinstance(store, ProvenanceStore):
        raise TypeError(
            f"find_in_provenance needs a ProvenanceStore, got "
            f"{type(store).__name__}")
    if not isinstance(query, MemoryQuery):
        raise TypeError(
            f"find_in_provenance needs a MemoryQuery, got "
            f"{type(query).__name__}")
    matched = store.scan(query.matches_record)
    matched.sort(key=lambda r: query._sort_key(r),
                 reverse=query.descending)
    start = query.offset
    end = None if query.limit is None else start + query.limit
    return matched[start:end]
