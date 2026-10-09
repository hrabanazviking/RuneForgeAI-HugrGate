"""Trace replay viewer data. Slice 347.

The replay viewer needs one thing: *every span of a trace, in order,
with nesting*.  :class:`TraceReplay` builds that from a
:class:`TraceStore <hugrgate.observability.trace.TraceStore>`:

- :meth:`timeline` — spans ordered by start time, each with its depth
  (nesting level derived from ``parent_span_id``), start offset in ms
  from the trace start, duration, status, and attributes;
- :meth:`to_dict` — the JSON document a viewer renders (waterfall,
  span detail pane, error highlighting);
- :meth:`render_text` — a plain-text waterfall for terminals and logs.

Orphan spans (parent id not in the trace) are kept at depth 0 and
flagged, never dropped — the viewer must show what the store has,
including ragged edges from sampling or eviction.
"""

from __future__ import annotations

import time
from typing import Any

from hugrgate.errors import TraceError
from hugrgate.observability.trace import Span, TraceStore

__all__ = [
    "TraceReplay",
]


class TraceReplay:
    """Assemble viewer-ready data for one trace."""

    def __init__(self, store: TraceStore) -> None:
        self._store = store

    def timeline(self, trace_id: str) -> list[dict[str, Any]]:
        """Ordered span entries with depth, offsets, and durations."""
        spans = self._store.get_trace(trace_id)
        if not spans:
            raise TraceError(f"no spans recorded for trace {trace_id!r}")
        by_id = {span.span_id: span for span in spans}
        base = min(span.start_time for span in spans)

        def _depth(span: Span, seen: set[str]) -> tuple[int, bool]:
            depth = 0
            orphan = False
            current = span
            while current.parent_span_id is not None:
                if current.parent_span_id in seen:
                    break  # cycle guard: malformed but renderable
                seen.add(current.span_id)
                parent = by_id.get(current.parent_span_id)
                if parent is None:
                    orphan = True
                    break
                depth += 1
                current = parent
            return depth, orphan

        entries = []
        for span in spans:
            depth, orphan = _depth(span, set())
            try:
                duration_ms = span.duration_s * 1000.0
            except TraceError:  # pragma: no cover - store holds finished
                duration_ms = 0.0
            entries.append({
                "name": span.name,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "depth": depth,
                "orphan": orphan,
                "start_offset_ms": round(
                    (span.start_time - base) * 1000.0, 3),
                "duration_ms": round(duration_ms, 3),
                "status": span.status,
                "attributes": span.attributes,
                "events": [
                    {"name": e["name"], "timestamp": e["timestamp"]}
                    for e in span.events
                ],
            })
        return entries

    def to_dict(self, trace_id: str) -> dict[str, Any]:
        """The viewer document: metadata + timeline."""
        entries = self.timeline(trace_id)
        total_ms = max((e["start_offset_ms"] + e["duration_ms"]
                        for e in entries), default=0.0)
        errors = sum(1 for e in entries if e["status"] != "ok")
        return {
            "trace_id": trace_id,
            "generated_at": time.time(),
            "span_count": len(entries),
            "total_duration_ms": round(total_ms, 3),
            "error_count": errors,
            "timeline": entries,
        }

    def render_text(self, trace_id: str) -> str:
        """Plain-text waterfall for terminals and logs."""
        entries = self.timeline(trace_id)
        lines = [f"trace {trace_id} ({len(entries)} spans)"]
        for entry in entries:
            indent = "  " * entry["depth"]
            marker = "!" if entry["status"] != "ok" else " "
            orphan = " [orphan]" if entry["orphan"] else ""
            lines.append(
                f"{marker} {indent}{entry['name']}"
                f" +{entry['start_offset_ms']:.1f}ms"
                f" ({entry['duration_ms']:.1f}ms){orphan}")
        return "\n".join(lines)
