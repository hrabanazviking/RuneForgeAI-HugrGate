"""Routing trace spans. Slice 331.

Renders the adaptive router's choice as a span: which candidates were
considered, which arm was pulled, with what propensity, under which
policy version — the exact fields :mod:`hugrgate.adaptive.telemetry`
logs as a :class:`RouteEvent`, so the trace and the learning dataset
tell the same story.

The builder accepts a real ``RouteEvent`` (preferred — schema-checked)
or a plain mapping with the same keys, so non-adaptive routers can
emit identical spans.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from hugrgate.adaptive.telemetry import RouteEvent
from hugrgate.errors import TraceError
from hugrgate.observability.trace import Span, SpanContext, Tracer

__all__ = [
    "ROUTING_SPAN_NAME",
    "annotate_routing",
    "routing_span",
]

#: Canonical span name for routing-decision spans.
ROUTING_SPAN_NAME = "hugrgate.routing"


def _as_mapping(event: RouteEvent | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(event, RouteEvent):
        return {
            "candidates": list(event.candidates),
            "propensities": dict(event.propensities),
            "chosen": event.chosen,
            "policy_version": event.policy_version,
            "privacy_class": event.privacy_class,
            "latency_ms": event.latency_ms,
            "cost": event.cost,
            "energy_wh": event.energy_wh,
            "shadow": event.shadow,
        }
    if not isinstance(event, Mapping):
        raise TraceError(
            f"routing event must be a RouteEvent or a mapping, got "
            f"{type(event).__name__}")
    return event


def annotate_routing(span: Span,
                     event: RouteEvent | Mapping[str, Any]) -> Span:
    """Attach routing-decision metadata to an open span."""
    data = _as_mapping(event)
    candidates = data.get("candidates")
    chosen = data.get("chosen")
    if not candidates or chosen not in candidates:
        raise TraceError(
            "routing event needs non-empty candidates containing 'chosen'")
    propensities = data.get("propensities") or {}
    propensity = propensities.get(chosen)
    span.set_attribute("routing.candidate_count", len(candidates))
    span.set_attribute("routing.chosen", str(chosen))
    span.set_attribute("routing.policy_version",
                       str(data.get("policy_version", "unknown")))
    span.set_attribute("routing.privacy_class",
                       str(data.get("privacy_class", "unknown")))
    span.set_attribute("routing.shadow", bool(data.get("shadow", False)))
    if propensity is not None:
        span.set_attribute("routing.propensity", round(float(propensity), 6))
    for key in ("latency_ms", "cost", "energy_wh"):
        value = data.get(key)
        if value is not None:
            span.set_attribute(f"routing.{key}", round(float(value), 6))
    span.add_event("routing.chosen", {
        "chosen": str(chosen),
        "candidate_count": len(candidates),
    })
    return span


@contextmanager
def routing_span(tracer: Tracer,
                 event: RouteEvent | Mapping[str, Any],
                 parent: Span | SpanContext | None = None
                 ) -> Iterator[Span]:
    """Open a routing span and annotate it from *event* on entry."""
    with tracer.trace(ROUTING_SPAN_NAME, parent=parent) as span:
        annotate_routing(span, event)
        yield span
