"""Edge telemetry lite — bounded, privacy-safe metrics. Slice 195.

Full observability stacks are too heavy for small boards, and raw
decision state must never leave the device in telemetry. :class:`TelemetryLite`
is the compromise:

- **fixed-size ring buffer** of numeric events (default 256) — memory
  is bounded no matter how long the node runs;
- **counters and gauges** for cheap aggregates without per-event cost;
- **numeric-only values**: :meth:`record` rejects strings, dicts, and
  other smuggled payloads — prompts, states, and PII cannot enter
  telemetry by construction, mirroring
  :class:`hugrgate.privacy.PrivacyGuard`'s retention rules;
- **compact export**: one JSON-serializable dict for the occasional
  uplink or the slice-196 benchmark harness.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import HugrGateError

__all__ = [
    "DEFAULT_MAX_EVENTS",
    "TelemetryError",
    "TelemetryEvent",
    "TelemetryLite",
]

#: Default ring-buffer capacity.
DEFAULT_MAX_EVENTS = 256


class TelemetryError(HugrGateError):
    """A telemetry invariant was violated."""


@dataclass(frozen=True)
class TelemetryEvent:
    """One numeric observation."""

    seq: int
    timestamp: float
    name: str
    value: float
    tags: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "timestamp": self.timestamp,
                "name": self.name, "value": self.value,
                "tags": [list(t) for t in self.tags]}


def _coerce_value(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise TelemetryError(
            f"telemetry value for {name!r} must be numeric, not bool")
    if isinstance(value, (int, float)):
        result = float(value)
        if result != result:  # NaN
            raise TelemetryError(
                f"telemetry value for {name!r} must not be NaN")
        return result
    raise TelemetryError(
        f"telemetry value for {name!r} must be numeric, got "
        f"{type(value).__name__}: raw payloads are never telemetered")


def _coerce_tags(tags: Mapping[str, str] | None, name: str
                 ) -> tuple[tuple[str, str], ...]:
    if tags is None:
        return ()
    if not isinstance(tags, Mapping):
        raise TelemetryError(f"tags for {name!r} must be a string mapping")
    out = []
    for k, v in tags.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise TelemetryError(
                f"tags for {name!r} must map str -> str")
        out.append((k, v))
    return tuple(out)


class TelemetryLite:
    """Bounded ring-buffer telemetry with counters and gauges."""

    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS,
                 clock: Callable[[], float] | None = None):
        if max_events < 1:
            raise TelemetryError("max_events must be >= 1")
        self._max_events = int(max_events)
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._events: deque[TelemetryEvent] = deque(maxlen=self._max_events)
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._seq = 0
        self._dropped = 0  # events evicted by the ring (bounded, counted)

    # -- recording ---------------------------------------------------------------

    def record(self, name: str, value: float,
               tags: Mapping[str, str] | None = None) -> TelemetryEvent:
        """Append one numeric event; oldest is evicted past capacity."""
        if not name or not name.strip():
            raise TelemetryError("event name must be non-empty")
        event = TelemetryEvent(
            seq=self._next_seq(), timestamp=self._clock(),
            name=name, value=_coerce_value(value, name),
            tags=_coerce_tags(tags, name))
        with self._lock:
            if len(self._events) == self._max_events:
                self._dropped += 1
            self._events.append(event)
        return event

    def count(self, name: str, delta: float = 1.0) -> float:
        """Add to a counter; returns the new total."""
        if not name or not name.strip():
            raise TelemetryError("counter name must be non-empty")
        delta = _coerce_value(delta, name)
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + delta
            return self._counters[name]

    def gauge(self, name: str, value: float) -> None:
        """Set a last-value gauge."""
        if not name or not name.strip():
            raise TelemetryError("gauge name must be non-empty")
        with self._lock:
            self._gauges[name] = _coerce_value(value, name)

    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    # -- export ----------------------------------------------------------------------

    def recent(self, n: int | None = None) -> list[TelemetryEvent]:
        """Newest-first snapshot of buffered events (up to ``n``)."""
        with self._lock:
            events = list(self._events)
        events.reverse()
        return events[:n] if n is not None else events

    def export(self) -> dict[str, Any]:
        """Compact, JSON-serializable snapshot for uplink or benchmarks."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "events": [e.to_dict() for e in self._events],
                "dropped_events": self._dropped,
                "max_events": self._max_events,
            }

    def reset(self) -> None:
        """Clear events, counters, and gauges (keeps the seq counter)."""
        with self._lock:
            self._events.clear()
            self._counters.clear()
            self._gauges.clear()
            self._dropped = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"buffered_events": len(self._events),
                    "max_events": self._max_events,
                    "dropped_events": self._dropped,
                    "counters": len(self._counters),
                    "gauges": len(self._gauges)}
