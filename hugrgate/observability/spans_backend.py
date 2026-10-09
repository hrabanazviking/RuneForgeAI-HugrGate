"""Backend trace spans. Slice 330.

Every backend invocation becomes a child span of the decision span:
``hugrgate.backend`` with the backend name, the attempt number (retries
get one span per attempt, linked to their siblings), and the outcome —
latency, success, or the machine-readable error code.

``backend_span`` records exceptions as span errors and re-raises, so the
retry loop in :mod:`hugrgate.chaos.retry` (or any caller) keeps its own
semantics while the trace shows exactly which attempt failed and why.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from hugrgate.errors import HugrGateError, TraceError
from hugrgate.observability.trace import Span, SpanContext, Tracer

__all__ = [
    "BACKEND_SPAN_NAME",
    "annotate_backend_outcome",
    "backend_span",
]

#: Canonical span name for backend-invocation spans.
BACKEND_SPAN_NAME = "hugrgate.backend"


def annotate_backend_outcome(span: Span, backend_name: str,
                             latency_ms: float, ok: bool,
                             error_code: str | None = None) -> Span:
    """Record the outcome of one backend attempt on an open span."""
    span.set_attribute("backend.name", backend_name)
    span.set_attribute("backend.latency_ms", round(max(0.0, latency_ms), 3))
    span.set_attribute("backend.ok", ok)
    if ok:
        span.add_event("backend.succeeded", {"backend": backend_name})
    else:
        code = error_code or "unknown"
        span.set_attribute("backend.error_code", code)
        span.add_event("backend.failed", {
            "backend": backend_name, "error_code": code})
        span.set_error(code)
    return span


@contextmanager
def backend_span(tracer: Tracer, backend_name: str, attempt: int = 1,
                 parent: Span | SpanContext | None = None,
                 extra_attributes: dict[str, Any] | None = None
                 ) -> Iterator[Span]:
    """Trace one backend attempt as a child of the ambient decision span.

    On exception the span is marked with the error's taxonomy ``code``
    (or the stdlib exception name) and the exception re-raised.
    """
    if attempt < 1:
        raise TraceError(f"backend attempt must be >= 1, got {attempt!r}")
    attributes: dict[str, Any] = {
        "backend.name": backend_name,
        "backend.attempt": attempt,
    }
    if extra_attributes:
        attributes.update(extra_attributes)
    with tracer.trace(BACKEND_SPAN_NAME, attributes=attributes,
                      parent=parent) as span:
        start = time.perf_counter()
        try:
            yield span
        except HugrGateError as exc:
            annotate_backend_outcome(
                span, backend_name,
                (time.perf_counter() - start) * 1000.0, False,
                error_code=exc.code)
            raise
        except Exception as exc:  # record, never swallow
            annotate_backend_outcome(
                span, backend_name,
                (time.perf_counter() - start) * 1000.0, False,
                error_code=type(exc).__name__)
            raise
        else:
            annotate_backend_outcome(
                span, backend_name,
                (time.perf_counter() - start) * 1000.0, True)
