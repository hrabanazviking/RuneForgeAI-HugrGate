"""Distributed trace model for HugrGate. Slice 328.

The stdlib-only, local-first trace core that
:mod:`hugrgate.observability.otel` bridges to OpenTelemetry:

- :class:`Span` — one timed operation with validated attributes,
  events, and a privacy-enforcing attribute gate (metadata only, never
  payload — the same law as :mod:`hugrgate.log`'s ``PRIVACY_RULE``);
- :class:`Tracer` — creates spans, propagates parent context, applies
  head-based sampling;
- :class:`TraceStore` — bounded in-memory store of finished spans with
  trace reassembly for the replay viewer (slice 347).

Sampling is deterministic per trace: the sampler hashes the trace id,
so a trace is either fully kept or fully dropped — never a ragged
half-trace.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import TraceError

__all__ = [
    "FORBIDDEN_ATTRIBUTE_KEYS",
    "ProbabilisticSampler",
    "Span",
    "SpanContext",
    "TraceStore",
    "Tracer",
    "new_span_id",
    "new_trace_id",
]

#: Attribute keys that may carry decision payloads or PII.  Spans log
#: *metadata* (backend names, verdicts, latencies) — never payload.
#: Setting one of these raises :class:`~hugrgate.errors.TraceError`.
FORBIDDEN_ATTRIBUTE_KEYS: frozenset[str] = frozenset({
    "state", "value", "input", "prompt", "payload", "text", "document",
    "secret", "password", "token", "pii",
})

_MAX_ATTRIBUTE_VALUE_LEN = 4096


def new_trace_id() -> str:
    """128-bit trace id as 32 lowercase hex chars (W3C compatible)."""
    return secrets.token_hex(16)


def new_span_id() -> str:
    """64-bit span id as 16 lowercase hex chars (W3C compatible)."""
    return secrets.token_hex(8)


def _require_jsonable(value: Any, name: str) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise TraceError(
            f"span attribute {name!r} is not JSON-serializable: {exc}"
        ) from exc


def _check_attribute(key: str, value: Any) -> None:
    if not isinstance(key, str) or not key:
        raise TraceError("span attribute keys must be non-empty strings")
    if key in FORBIDDEN_ATTRIBUTE_KEYS:
        raise TraceError(
            f"span attribute {key!r} is forbidden: spans carry metadata, "
            f"never payload (see hugrgate.log PRIVACY_RULE)")
    _require_jsonable(value, key)
    if isinstance(value, str) and len(value) > _MAX_ATTRIBUTE_VALUE_LEN:
        raise TraceError(
            f"span attribute {key!r} exceeds "
            f"{_MAX_ATTRIBUTE_VALUE_LEN} chars")


@dataclass(frozen=True)
class SpanContext:
    """Immutable propagation context for one span."""

    trace_id: str
    span_id: str
    sampled: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", self.trace_id):
            raise TraceError(f"bad trace_id: {self.trace_id!r}")
        if not re.fullmatch(r"[0-9a-f]{16}", self.span_id):
            raise TraceError(f"bad span_id: {self.span_id!r}")


class Span:
    """One timed operation in a trace.

    A span is *mutable* until :meth:`finish` and frozen afterwards;
    mutating a finished span raises :class:`~hugrgate.errors.TraceError`.
    Times are ``time.time()`` seconds (wall clock) so spans line up with
    log timestamps; durations use the monotonic delta recorded at
    finish.
    """

    def __init__(self, name: str, context: SpanContext,
                 parent_span_id: str | None = None,
                 attributes: Mapping[str, Any] | None = None,
                 start_time: float | None = None) -> None:
        if not name:
            raise TraceError("span name must be non-empty")
        self._name = name
        self._context = context
        self._parent_span_id = parent_span_id
        self._attributes: dict[str, Any] = {}
        for key, value in dict(attributes or {}).items():
            _check_attribute(key, value)
            self._attributes[key] = value
        self._events: list[dict[str, Any]] = []
        self._links: list[dict[str, str]] = []
        self._status = "ok"
        self._start_time = start_time if start_time is not None else time.time()
        self._start_mono = time.perf_counter()
        self._end_time: float | None = None
        self._duration_s: float | None = None
        self._finished = False
        self._dropped = False

    # -- read-only surface -------------------------------------------------
    @property
    def name(self) -> str:
        return self._name

    @property
    def trace_id(self) -> str:
        return self._context.trace_id

    @property
    def span_id(self) -> str:
        return self._context.span_id

    @property
    def parent_span_id(self) -> str | None:
        return self._parent_span_id

    @property
    def sampled(self) -> bool:
        return self._context.sampled

    @property
    def attributes(self) -> dict[str, Any]:
        return dict(self._attributes)

    @property
    def events(self) -> list[dict[str, Any]]:
        return [dict(e) for e in self._events]

    @property
    def status(self) -> str:
        return self._status

    @property
    def start_time(self) -> float:
        return self._start_time

    @property
    def end_time(self) -> float:
        if self._end_time is None:
            raise TraceError("span has not finished yet")
        return self._end_time

    @property
    def duration_s(self) -> float:
        if self._duration_s is None:
            raise TraceError("span has not finished yet")
        return self._duration_s

    @property
    def finished(self) -> bool:
        return self._finished

    def context(self) -> SpanContext:
        return self._context

    # -- mutation ----------------------------------------------------------
    def _ensure_open(self) -> None:
        if self._finished:
            raise TraceError(f"span {self._name!r} is already finished")

    def set_attribute(self, key: str, value: Any) -> Span:
        self._ensure_open()
        _check_attribute(key, value)
        self._attributes[key] = value
        return self

    def add_event(self, name: str,
                  attributes: Mapping[str, Any] | None = None) -> Span:
        self._ensure_open()
        if not name:
            raise TraceError("span event name must be non-empty")
        event_attrs: dict[str, Any] = {}
        for key, value in dict(attributes or {}).items():
            _check_attribute(key, value)
            event_attrs[key] = value
        self._events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": event_attrs,
        })
        return self

    def add_link(self, trace_id: str, span_id: str) -> Span:
        """Causal link to another span (e.g. the retried attempt)."""
        self._ensure_open()
        SpanContext(trace_id=trace_id, span_id=span_id)  # validates format
        self._links.append({"trace_id": trace_id, "span_id": span_id})
        return self

    def set_error(self, message: str) -> Span:
        self._ensure_open()
        self._status = f"error: {message}" if message else "error"
        return self

    def finish(self, end_time: float | None = None) -> Span:
        self._ensure_open()
        now = time.time()
        self._end_time = end_time if end_time is not None else now
        if self._end_time < self._start_time:
            raise TraceError("span end_time precedes start_time")
        self._duration_s = max(0.0, time.perf_counter() - self._start_mono)
        self._finished = True
        return self

    def mark_dropped(self) -> None:
        """Internal: flag this span as sampled-out.

        Called by :class:`Tracer` for spans the sampler rejected; the
        span still runs its full lifecycle but is dropped at finish
        instead of stored.
        """
        self._dropped = True

    @property
    def dropped(self) -> bool:
        return self._dropped

    # -- export ------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        if not self._finished:
            raise TraceError("cannot export an unfinished span")
        return {
            "name": self._name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self._parent_span_id,
            "start_time": self._start_time,
            "end_time": self._end_time,
            "duration_s": self._duration_s,
            "attributes": dict(self._attributes),
            "events": [dict(e) for e in self._events],
            "links": [dict(link) for link in self._links],
            "status": self._status,
            "sampled": self._context.sampled,
        }


class ProbabilisticSampler:
    """Head-based sampler: deterministic per trace id.

    ``should_sample(trace_id)`` hashes the trace id and compares
    against ``rate`` — the same trace always gets the same verdict, so
    traces are kept whole or dropped whole.
    """

    def __init__(self, rate: float = 1.0) -> None:
        if not 0.0 <= rate <= 1.0:
            raise TraceError(
                f"sampler rate must be in [0, 1], got {rate!r}")
        self._rate = rate

    @property
    def rate(self) -> float:
        return self._rate

    def should_sample(self, trace_id: str) -> bool:
        if self._rate >= 1.0:
            return True
        if self._rate <= 0.0:
            return False
        digest = hashlib.sha256(trace_id.encode("ascii")).digest()
        point = int.from_bytes(digest[:8], "big") / 2**64
        return point < self._rate


class TraceStore:
    """Bounded in-memory store of finished spans.

    Oldest spans evict first when ``max_spans`` is reached.
    :meth:`get_trace` reassembles one trace's spans in start-time
    order — the input the replay viewer (slice 347) renders.
    Thread-safe.
    """

    def __init__(self, max_spans: int = 10000) -> None:
        if not isinstance(max_spans, int) or max_spans < 1:
            raise TraceError("TraceStore.max_spans must be a positive int")
        self._max_spans = max_spans
        self._lock = threading.Lock()
        self._spans: deque[Span] = deque()

    def add(self, span: Span) -> None:
        if not span.finished:
            raise TraceError("TraceStore only accepts finished spans")
        with self._lock:
            self._spans.append(span)
            while len(self._spans) > self._max_spans:
                self._spans.popleft()

    def get_trace(self, trace_id: str) -> list[Span]:
        with self._lock:
            spans = [s for s in self._spans if s.trace_id == trace_id]
        return sorted(spans, key=lambda s: s.start_time)

    def find_spans(self, name: str) -> list[Span]:
        with self._lock:
            return [s for s in self._spans if s.name == name]

    def __len__(self) -> int:
        with self._lock:
            return len(self._spans)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


class Tracer:
    """Creates spans with parent propagation and sampling.

    ``current`` tracks the ambient span per thread (contextvars-free on
    purpose: HugrGate backends may hop threads).  Use :meth:`trace` as
    a context manager or decorator; finished spans land in the store.
    """

    def __init__(self, store: TraceStore | None = None,
                 sampler: ProbabilisticSampler | None = None,
                 service_name: str = "hugrgate") -> None:
        self._store = store or TraceStore()
        self._sampler = sampler or ProbabilisticSampler()
        self._service_name = service_name
        self._local = threading.local()

    @property
    def store(self) -> TraceStore:
        return self._store

    def _current(self) -> Span | None:
        return getattr(self._local, "span", None)

    def start_span(self, name: str,
                   attributes: Mapping[str, Any] | None = None,
                   parent: Span | SpanContext | None = None,
                   trace_id: str | None = None) -> Span:
        """Start a child of *parent* (or of the ambient span, or a root).

        An explicit W3C-decoded ``SpanContext`` may be passed as
        *parent* to continue a remote trace; pass ``trace_id`` to force
        a specific trace id (used by the sampler determinism tests).
        """
        ambient = self._current()
        if parent is None:
            parent = ambient
        if isinstance(parent, Span):
            trace_id = parent.trace_id
            parent_span_id: str | None = parent.span_id
            sampled = parent.sampled
        elif isinstance(parent, SpanContext):
            trace_id = parent.trace_id
            parent_span_id = parent.span_id
            sampled = parent.sampled
        else:
            trace_id = trace_id or new_trace_id()
            parent_span_id = None
            sampled = self._sampler.should_sample(trace_id)
        span = Span(name, SpanContext(trace_id=trace_id,
                                     span_id=new_span_id(),
                                     sampled=sampled),
                    parent_span_id=parent_span_id,
                    attributes={"service.name": self._service_name,
                                **dict(attributes or {})})
        if not sampled:
            # Unsampled spans still run their lifecycle (attributes,
            # timing) but are dropped at finish instead of stored.
            span.mark_dropped()
        return span

    @contextmanager
    def trace(self, name: str,
              attributes: Mapping[str, Any] | None = None,
              parent: Span | SpanContext | None = None) -> Iterator[Span]:
        """Context manager: finish the span (and store it) on exit.

        Exceptions are recorded as span errors and re-raised — the
        tracer never swallows application failures.
        """
        span = self.start_span(name, attributes=attributes, parent=parent)
        previous = self._current()
        self._local.span = span
        try:
            yield span
        except Exception as exc:
            span.set_error(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            self._local.span = previous
            span.finish()
            if not span.dropped:
                self._store.add(span)

    def traced(self, name: str | None = None) -> Callable:
        """Decorator form of :meth:`trace`."""

        def decorator(func: Callable) -> Callable:
            span_name = name or f"{func.__module__}.{func.__qualname__}"

            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.trace(span_name):
                    return func(*args, **kwargs)

            wrapper.__name__ = getattr(func, "__name__", "wrapper")
            wrapper.__doc__ = func.__doc__
            return wrapper

        return decorator
