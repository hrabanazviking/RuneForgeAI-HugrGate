"""Trace correlation. Slice 222.

Every cluster envelope already carries a ``trace_id``; this module
turns it into real distributed tracing:

- :class:`TraceContext` — ``(trace_id, span_id, parent_span_id,
  node_id)``. ``root()`` starts a trace, ``child()`` nests a span.
  The context rides the wire inside decide payloads (``"trace"`` key,
  additive and backward compatible).
- :class:`Span` — one finished unit of work: operation name, wall-
  clock timestamps, ``ok`` / ``error`` / ``abstained`` status, and
  free-form attributes. Strict ``to_dict`` / ``from_dict``.
- :class:`TraceCollector` — the per-node span sink: ``start()`` a
  span, ``finish()`` it, ``spans_for(trace_id)`` in time order, and
  ``trace_tree(trace_id)`` assembling parent/child nesting across
  nodes. Bounded; oldest spans evict first.
- ``TRACE_SPAN`` — push spans to a peer (a central collector);
  ``RPCClient.send_spans`` + ``node.handle_trace_span``.

Instrumented: ``decide_remote`` (client span) → ``handle_decide``
(server span, child of the caller's context).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from hugrgate.cluster.protocol import new_trace_id
from hugrgate.errors import SpecError

__all__ = [
    "DEFAULT_TRACE_MAX_SPANS",
    "Span",
    "TraceCollector",
    "TraceContext",
    "new_span_id",
]

#: Spans kept per collector before the oldest evict.
DEFAULT_TRACE_MAX_SPANS = 10_000


def new_span_id() -> str:
    """Fresh 64-bit span id (hex)."""
    return f"{time.time_ns():016x}"[-16:]


def _check_hex(value: Any, length: int, name: str) -> str:
    if (not isinstance(value, str) or len(value) != length
            or any(c not in "0123456789abcdef" for c in value)):
        raise SpecError(
            f"{name} must be a {length}-char lowercase hex string, got "
            f"{value!r}")
    return value


@dataclass
class TraceContext:
    """Where a span lives: trace, span, parent, node."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    node_id: str

    @classmethod
    def root(cls, node_id: str,
             trace_id: str | None = None) -> TraceContext:
        """Start a new trace on this node."""
        return cls(trace_id=trace_id or new_trace_id(),
                   span_id=new_span_id(), parent_span_id=None,
                   node_id=_check_hex(node_id, 64, "node_id"))

    def child(self) -> TraceContext:
        """Nest a span under this context."""
        return TraceContext(trace_id=self.trace_id,
                            span_id=new_span_id(),
                            parent_span_id=self.span_id,
                            node_id=self.node_id)

    def to_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "node_id": self.node_id}

    @classmethod
    def from_dict(cls, raw: Any) -> TraceContext:
        if not isinstance(raw, dict):
            raise SpecError(f"trace context must be an object, got {raw!r}")
        try:
            trace_id = _check_hex(raw["trace_id"], 32, "trace_id")
            span_id = _check_hex(raw["span_id"], 16, "span_id")
            node_id = _check_hex(raw["node_id"], 64, "node_id")
        except KeyError as e:
            raise SpecError(
                f"trace context missing key: {e.args[0]}") from e
        parent = raw.get("parent_span_id")
        if parent is not None:
            parent = _check_hex(parent, 16, "parent_span_id")
        return cls(trace_id=trace_id, span_id=span_id,
                   parent_span_id=parent, node_id=node_id)


@dataclass
class Span:
    """One finished unit of work."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    node_id: str
    operation: str
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    _collector: Any = field(default=None, repr=False, compare=False)

    def finish(self, status: str = "ok",
               attributes: dict[str, Any] | None = None) -> float:
        """Close the span, record it, return duration in ms."""
        if status not in ("ok", "error", "abstained"):
            raise SpecError(f"bad span status {status!r}")
        self.status = status
        if attributes:
            self.attributes.update(attributes)
        self.ended_at = time.time()
        if self._collector is not None:
            self._collector.record(self)
            self._collector = None
        return self.duration_ms()

    def duration_ms(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.time()
        return max(0.0, (end - self.started_at) * 1000.0)

    def to_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "node_id": self.node_id, "operation": self.operation,
                "started_at": self.started_at, "ended_at": self.ended_at,
                "status": self.status,
                "attributes": dict(self.attributes)}

    @classmethod
    def from_dict(cls, raw: Any) -> Span:
        if not isinstance(raw, dict):
            raise SpecError(f"span must be an object, got {raw!r}")
        try:
            trace_id = _check_hex(raw["trace_id"], 32, "trace_id")
            span_id = _check_hex(raw["span_id"], 16, "span_id")
            node_id = _check_hex(raw["node_id"], 64, "node_id")
            operation = raw["operation"]
        except KeyError as e:
            raise SpecError(
                f"span missing key: {e.args[0]}") from e
        if not isinstance(operation, str) or not operation:
            raise SpecError("span needs a non-empty 'operation'")
        parent = raw.get("parent_span_id")
        if parent is not None:
            parent = _check_hex(parent, 16, "parent_span_id")
        status = raw.get("status", "ok")
        if status not in ("ok", "error", "abstained"):
            raise SpecError(f"bad span status {status!r}")
        attributes = raw.get("attributes", {})
        if not isinstance(attributes, dict):
            raise SpecError("span 'attributes' must be an object")
        return cls(trace_id=trace_id, span_id=span_id,
                   parent_span_id=parent, node_id=node_id,
                   operation=operation,
                   started_at=float(raw.get("started_at", time.time())),
                   ended_at=raw.get("ended_at"),
                   status=status, attributes=dict(attributes))


class TraceCollector:
    """Per-node span sink with trace assembly. Thread-safe."""

    def __init__(self, max_spans: int = DEFAULT_TRACE_MAX_SPANS) -> None:
        if not isinstance(max_spans, int) or max_spans < 1:
            raise SpecError("max_spans must be a positive int")
        self._max_spans = max_spans
        self._spans: list[Span] = []
        self._lock = threading.RLock()

    def start(self, context: TraceContext, operation: str,
              attributes: dict[str, Any] | None = None) -> Span:
        """Open a span; :meth:`Span.finish` records it here."""
        if not isinstance(context, TraceContext):
            raise SpecError(f"context must be a TraceContext, got {context!r}")
        if not isinstance(operation, str) or not operation:
            raise SpecError("span needs a non-empty operation")
        return Span(trace_id=context.trace_id, span_id=context.span_id,
                    parent_span_id=context.parent_span_id,
                    node_id=context.node_id, operation=operation,
                    attributes=dict(attributes) if attributes else {},
                    _collector=self)

    def record(self, span: Span) -> None:
        """Record an already-finished span (e.g. pushed by a peer)."""
        if not isinstance(span, Span):
            raise SpecError(f"can only record Span, got {span!r}")
        with self._lock:
            self._spans.append(span)
            while len(self._spans) > self._max_spans:
                self._spans.pop(0)

    def spans_for(self, trace_id: str) -> list[Span]:
        """Spans of one trace, oldest first."""
        with self._lock:
            spans = [s for s in self._spans if s.trace_id == trace_id]
        return sorted(spans, key=lambda s: s.started_at)

    def trace_tree(self, trace_id: str) -> list[dict[str, Any]]:
        """Nested ``{"span": ..., "children": [...]}`` forest by parent."""
        nodes: dict[str, dict[str, Any]] = {}
        for span in self.spans_for(trace_id):
            nodes[span.span_id] = {"span": span.to_dict(), "children": []}
        roots: list[dict[str, Any]] = []
        for span in self.spans_for(trace_id):
            node = nodes[span.span_id]
            parent = (nodes.get(span.parent_span_id)
                      if span.parent_span_id else None)
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return roots

    def count(self) -> int:
        with self._lock:
            return len(self._spans)

    def clear(self, trace_id: str | None = None) -> int:
        """Drop spans (one trace, or all). Returns the count dropped."""
        with self._lock:
            if trace_id is None:
                dropped = len(self._spans)
                self._spans.clear()
                return dropped
            kept = [s for s in self._spans if s.trace_id != trace_id]
            dropped = len(self._spans) - len(kept)
            self._spans = kept
            return dropped
