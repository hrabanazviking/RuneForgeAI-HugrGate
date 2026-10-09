"""Agent Nervous System (Campaign XVI) — attention prioritization.

Slice 383.  Triage (377) defers non-urgent work; something must
decide *what the agent looks at next*.  :class:`AttentionPrioritizer`
is a bounded scored queue — the nervous system's spotlight:

``score = w_priority * priority_rank + w_urgency * urgency
        + w_novelty * novelty - w_cost * cost``

- ``priority`` is the signal's own urgency ladder (376);
- ``urgency`` is deadline pressure (0..1);
- ``novelty`` rewards unseen situations over repeats (0..1);
- ``cost`` penalizes expensive work so cheap wins don't starve
  behind dear ones (0..1).

The queue is bounded (``max_items``): when full, the lowest-scored
item is shed and counted — attention is finite and the system says
so explicitly rather than growing a queue forever.  Ordering is
deterministic: score first, then enqueue time, then id.
:class:`AttentionItem` is frozen; :meth:`reprioritize` replaces an
item's urgency/novelty in place by id.
"""

from __future__ import annotations

import heapq
import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.agents.types import PRIORITIES, PRIORITY_RANK

__all__ = [
    "AttentionConfig",
    "AttentionItem",
    "AttentionPrioritizer",
]


@dataclass(frozen=True)
class AttentionConfig:
    """Scoring weights and the attention budget."""

    w_priority: float = 2.0
    w_urgency: float = 3.0
    w_novelty: float = 1.5
    w_cost: float = 1.0
    max_items: int = 256

    def __post_init__(self) -> None:
        if self.max_items < 1:
            raise ValueError("max_items must be >= 1")
        for name in ("w_priority", "w_urgency", "w_novelty", "w_cost"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")


@dataclass(frozen=True)
class AttentionItem:
    """One unit of work competing for attention."""

    item_id: str
    topic: str
    priority: str = "normal"
    urgency: float = 0.5
    novelty: float = 0.5
    cost: float = 0.5
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id must be non-empty")
        if self.priority not in PRIORITY_RANK:
            raise ValueError(f"unknown priority {self.priority!r}")
        for name in ("urgency", "novelty", "cost"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")


class AttentionPrioritizer:
    """Bounded scored queue: the agent's spotlight."""

    def __init__(
        self,
        config: AttentionConfig | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or AttentionConfig()
        self._clock = clock or time.monotonic
        self._seq = itertools.count()
        # heap entries: (-score, enqueued_at, seq, item)
        self._heap: list[tuple[float, float, int, AttentionItem]] = []
        self._by_id: dict[str, AttentionItem] = {}
        self._stats = {"pushed": 0, "popped": 0, "dropped_overflow": 0,
                       "reprioritized": 0}

    def score(self, item: AttentionItem) -> float:
        """The attention score of ``item`` (higher = look here first)."""
        c = self._config
        return (
            c.w_priority * PRIORITY_RANK[item.priority]
            + c.w_urgency * item.urgency
            + c.w_novelty * item.novelty
            - c.w_cost * item.cost
        )

    def push(self, item: AttentionItem) -> str:
        """Enqueue ``item``; sheds the lowest-scored item when full.

        Returns ``"queued"`` or the ``item_id`` shed on overflow
        (``"shed-self"`` when the new item itself was the lowest).
        """
        if item.item_id in self._by_id:
            raise ValueError(f"duplicate item_id {item.item_id!r}")
        self._stats["pushed"] += 1
        entry = (-self.score(item), self._clock(), next(self._seq), item)
        if len(self._heap) >= self._config.max_items:
            worst = max(self._heap, key=lambda e: e[0])
            if entry[0] >= worst[0]:
                # New item scores lowest (or ties at the bottom): shed it.
                self._stats["dropped_overflow"] += 1
                return "shed-self"
            self._drop(worst[3].item_id)
            self._stats["dropped_overflow"] += 1
            shed_id = worst[3].item_id
        else:
            shed_id = ""
        heapq.heappush(self._heap, entry)
        self._by_id[item.item_id] = item
        return shed_id or "queued"

    def _drop(self, item_id: str) -> None:
        self._by_id.pop(item_id, None)
        self._heap = [e for e in self._heap if e[3].item_id != item_id]
        heapq.heapify(self._heap)

    def pop(self) -> AttentionItem | None:
        """Remove and return the highest-scored item (None when empty)."""
        while self._heap:
            _, _, _, item = heapq.heappop(self._heap)
            if self._by_id.pop(item.item_id, None) is not None:
                self._stats["popped"] += 1
                return item
        return None

    def peek(self) -> AttentionItem | None:
        """Highest-scored item without removing it (None when empty)."""
        while self._heap:
            _, _, _, item = self._heap[0]
            if item.item_id in self._by_id:
                return item
            heapq.heappop(self._heap)  # stale entry
        return None

    def reprioritize(
        self,
        item_id: str,
        *,
        urgency: float | None = None,
        novelty: float | None = None,
        priority: str | None = None,
    ) -> bool:
        """Replace an item's scoring inputs; True when it existed."""
        old = self._by_id.get(item_id)
        if old is None:
            return False
        new = AttentionItem(
            item_id=old.item_id,
            topic=old.topic,
            priority=priority or old.priority,
            urgency=old.urgency if urgency is None else urgency,
            novelty=old.novelty if novelty is None else novelty,
            cost=old.cost,
            payload=dict(old.payload),
        )
        self._drop(item_id)
        heapq.heappush(
            self._heap, (-self.score(new), self._clock(), next(self._seq), new)
        )
        self._by_id[item_id] = new
        self._stats["reprioritized"] += 1
        return True

    def __len__(self) -> int:
        return len(self._by_id)

    def stats(self) -> dict[str, int]:
        """Cumulative counters (copy)."""
        return dict(self._stats)

    def priorities(self) -> tuple[str, ...]:
        """The priority ladder (re-exported for callers)."""
        return PRIORITIES
