"""Shared structural types for the memory package. Slice 307.

Spoke modules (query, similarity, retrieval, ...) must never import
``hugrgate.memory.history`` — not even under ``TYPE_CHECKING`` —
because the import-cycle gate counts every static edge while
``history`` is the hub that imports the spokes. These Protocols keep
the spokes typed without creating a cycle: ``Episode`` and
``DecisionHistory`` satisfy them structurally, so no runtime
``isinstance`` games are needed.
"""

from __future__ import annotations

from typing import Any, Protocol

from hugrgate.provenance import DecisionRecord

__all__ = [
    "EpisodeLike",
    "HistoryLike",
]


class EpisodeLike(Protocol):
    """Structural shape of :class:`hugrgate.memory.history.Episode`."""

    episode_id: str
    record: DecisionRecord
    recorded_at: float
    privacy_class: str
    tags: tuple[str, ...]
    outcome: Any
    ground_truth: Any
    annotations: dict[str, Any]


class HistoryLike(Protocol):
    """Structural shape of :class:`hugrgate.memory.history.DecisionHistory`."""

    def find(self, query: Any) -> list[EpisodeLike]:
        """Run a query; return episode copies."""
        ...  # pragma: no cover - protocol stub

    def get(self, episode_id: str) -> EpisodeLike:
        """Return one episode copy; raise when unknown."""
        ...  # pragma: no cover - protocol stub

    def recent(self, n: int = 10) -> list[EpisodeLike]:
        """Chronological episode copies (newest last)."""
        ...  # pragma: no cover - protocol stub

    def by_request_hash(self, request_hash: str) -> list[EpisodeLike]:
        """Episode copies matching a provenance request hash."""
        ...  # pragma: no cover - protocol stub

    def record(self, *args: Any, **kwargs: Any) -> Any:
        """Remember a decision (owner role in guarded use)."""
        ...  # pragma: no cover - protocol stub

    def attach_outcome(self, *args: Any, **kwargs: Any) -> Any:
        """Attach an outcome (owner role in guarded use)."""
        ...  # pragma: no cover - protocol stub

    def attach_ground_truth(self, *args: Any, **kwargs: Any) -> Any:
        """Attach ground truth (owner role in guarded use)."""
        ...  # pragma: no cover - protocol stub

    def clear(self) -> Any:
        """Remove all episodes (owner role in guarded use)."""
        ...  # pragma: no cover - protocol stub
