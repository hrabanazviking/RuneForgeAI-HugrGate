"""Agent Nervous System (Campaign XVI) — the event bus.

Slice 376 (shared substrate).  The bus is the spinal cord: every
reactive trigger, state propagation, and inter-component signal in
slices 377-400 travels as an :class:`AgentSignal` over
:class:`EventBus`.

Design:

- Topic patterns: exact (``"agent.escalated"``), prefix
  (``"agent.*"``), or catch-all (``"*"``).  Handlers run in
  subscription-priority order, highest first; ties break by
  subscription order (deterministic).
- Dedup: a signal carrying ``dedup_key`` is delivered at most once
  per ``dedup_window_s`` — alert-storm protection inherited from the
  observability :class:`AlertManager` philosophy.
- Backpressure: ``max_pending`` bounds re-entrant publish depth
  (in-flight deliveries); policy ``"raise"`` surfaces
  :class:`BackpressureError`, ``"drop-oldest"`` sheds the incoming
  signal and counts it.
- Handler exceptions never propagate to the publisher; they are
  collected on the delivery report.  A dead handler must not kill
  the nervous system.
- Thread-safe: a single re-entrant lock guards subscriptions,
  dedup state, and stats.

The bus intentionally does *not* persist — durability belongs to
decision memory (:mod:`hugrgate.memory`), which subscribers can
write to through the memory-write gate (slice 380).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hugrgate.agents.types import AgentDelivery, AgentSignal
from hugrgate.errors import BackpressureError

__all__ = [
    "EventBus",
    "Subscription",
    "matches",
]

#: Handler signature: receives the signal, returns nothing meaningful.
Handler = Callable[[AgentSignal], Any]


def matches(pattern: str, topic: str) -> bool:
    """Return True when a subscription ``pattern`` matches ``topic``.

    Patterns: exact (``"a.b"``), prefix (``"a.*"`` matches ``"a"``
    and everything below it), suffix (``"*.heartbeat"`` matches any
    topic ending in ``".heartbeat"``), or catch-all (``"*"``).
    """
    if pattern == "*" or pattern == topic:
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return topic == prefix or topic.startswith(prefix + ".")
    if pattern.startswith("*."):
        return topic.endswith(pattern[1:])
    return False


@dataclass
class Subscription:
    """A live subscription; keep the token to unsubscribe."""

    token: int
    pattern: str
    priority: int


class EventBus:
    """Synchronous in-process event bus for the agent nervous system."""

    def __init__(
        self,
        *,
        dedup_window_s: float = 60.0,
        max_pending: int = 1024,
        backpressure: str = "raise",
        clock: Callable[[], float] | None = None,
    ) -> None:
        if dedup_window_s < 0:
            raise ValueError("dedup_window_s must be >= 0")
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        if backpressure not in ("raise", "drop-oldest"):
            raise ValueError("backpressure must be 'raise' or 'drop-oldest'")
        self._dedup_window_s = dedup_window_s
        self._max_pending = max_pending
        self._backpressure = backpressure
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._subs: dict[int, tuple[str, Handler, int]] = {}
        self._next_token = 1
        self._dedup: dict[str, float] = {}
        self._depth = 0
        self._stats = {
            "published": 0,
            "delivered": 0,
            "suppressed_dedup": 0,
            "dropped_backpressure": 0,
            "handler_errors": 0,
        }

    # -- subscriptions -------------------------------------------------
    def subscribe(
        self, pattern: str, handler: Handler, *, priority: int = 0
    ) -> Subscription:
        """Subscribe ``handler`` to topics matching ``pattern``."""
        if not pattern:
            raise ValueError("pattern must be non-empty")
        if not callable(handler):
            raise ValueError("handler must be callable")
        with self._lock:
            token = self._next_token
            self._next_token += 1
            self._subs[token] = (pattern, handler, priority)
        return Subscription(token=token, pattern=pattern, priority=priority)

    def unsubscribe(self, sub: Subscription) -> bool:
        """Remove a subscription; True when it existed."""
        with self._lock:
            return self._subs.pop(sub.token, None) is not None

    def subscription_count(self) -> int:
        """Number of live subscriptions."""
        with self._lock:
            return len(self._subs)

    # -- publishing ----------------------------------------------------
    def publish(self, signal: AgentSignal) -> AgentDelivery:
        """Deliver ``signal`` to matching handlers synchronously."""
        now = self._clock()
        with self._lock:
            self._stats["published"] += 1
            if signal.dedup_key:
                seen_at = self._dedup.get(signal.dedup_key)
                if seen_at is not None and now - seen_at < self._dedup_window_s:
                    self._stats["suppressed_dedup"] += 1
                    return AgentDelivery(signal=signal, suppressed=1)
                self._dedup[signal.dedup_key] = now
                self._prune_dedup(now)
            if self._depth >= self._max_pending:
                if self._backpressure == "raise":
                    raise BackpressureError(
                        f"event bus saturated ({self._max_pending} in flight)",
                        pending=self._depth,
                    )
                self._stats["dropped_backpressure"] += 1
                return AgentDelivery(signal=signal, dropped=1)
            self._depth += 1
            targets = sorted(
                (
                    (prio, token, handler)
                    for token, (pattern, handler, prio) in self._subs.items()
                    if matches(pattern, signal.topic)
                ),
                key=lambda t: (-t[0], t[1]),
            )
        delivered = 0
        errors: list[str] = []
        try:
            for _, token, handler in targets:
                try:
                    handler(signal)
                    delivered += 1
                except Exception as exc:  # noqa: BLE001 - isolated per handler
                    errors.append(f"handler#{token}: {exc}")
        finally:
            with self._lock:
                self._depth -= 1
                self._stats["delivered"] += delivered
                self._stats["handler_errors"] += len(errors)
        return AgentDelivery(
            signal=signal,
            delivered=delivered,
            suppressed=0,
            errors=tuple(errors),
        )

    def _prune_dedup(self, now: float) -> None:
        expired = [
            k for k, seen in self._dedup.items()
            if now - seen >= self._dedup_window_s
        ]
        for k in expired:
            del self._dedup[k]

    def stats(self) -> dict[str, int]:
        """Cumulative bus counters (copy)."""
        with self._lock:
            return dict(self._stats)

    def reset_stats(self) -> None:
        """Zero the cumulative counters (tests / rollover)."""
        with self._lock:
            for k in self._stats:
                self._stats[k] = 0
            self._dedup.clear()
