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
