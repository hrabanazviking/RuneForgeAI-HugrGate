"""Decision trace spans. Slice 329.

Renders one HugrGate decision as a trace span: the spec that was asked,
the policy that judged it, and the verdict that resulted — metadata
only, never the decision payload (``result.value`` and the full
distribution stay out of spans by construction).

The span name is ``hugrgate.decision``; the verdict is recorded both as
an attribute (``decision.verdict``) and as a span event
(``decision.accepted`` / ``decision.review`` / ``decision.abstained``)
so the replay viewer (slice 347) can filter on it.

Use as a context manager::

    with decision_span(tracer, spec, policy) as span:
        result = gate.decide(spec)
    annotate_decision(span, spec, result, policy)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from hugrgate.errors import TraceError
from hugrgate.observability.trace import Span, SpanContext, Tracer
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DECISION_SPAN_NAME",
    "annotate_decision",
    "decision_span",
    "probability_band",
    "verdict_of",
]

#: Canonical span name for decision spans.
DECISION_SPAN_NAME = "hugrgate.decision"


def probability_band(probability: float) -> str:
    """Bucket a probability into a 0.1-wide band label (metadata-safe)."""
    if not 0.0 <= probability <= 1.0:
        raise TraceError(
            f"probability_band: probability out of bounds: {probability!r}")
    lo = min(int(probability * 10), 9)
    return f"{lo / 10:.1f}-{(lo + 1) / 10:.1f}"


def verdict_of(result: DecisionResult) -> str:
    """Machine-readable verdict: accept | review | abstain."""
    if not result.accepted:
        return "abstain"
    reason = str(result.metadata.get("policy_verdict", "accept"))
    return reason if reason in ("accept", "review") else "accept"


def annotate_decision(span: Span, spec: DecisionSpec,
                      result: DecisionResult,
                      policy: DecisionPolicy | None = None) -> Span:
    """Attach decision metadata to an open span; returns the span."""
    span.set_attribute("decision.spec_type", spec.type)
    span.set_attribute("decision.backend", result.backend)
    span.set_attribute("decision.model", result.model)
    span.set_attribute("decision.verdict", verdict_of(result))
    span.set_attribute("decision.probability_band",
                       probability_band(result.probability))
    span.set_attribute("decision.uncertainty", round(result.uncertainty, 4))
    span.set_attribute("decision.latency_ms", round(result.latency_ms, 3))
    span.set_attribute("decision.fallback_used", result.fallback_used)
    span.set_attribute("decision.calibration_profile",
                       result.calibration_profile)
    if policy is not None:
        span.set_attribute("decision.policy_min_probability",
                           policy.minimum_probability)
        span.set_attribute("decision.policy_privacy_class",
                           policy.privacy_class)
        span.set_attribute("decision.policy_fallback",
                           policy.fallback_behavior)
    verdict = verdict_of(result)
    span.add_event(f"decision.{verdict}", {
        "probability_band": probability_band(result.probability),
        "backend": result.backend,
    })
    if not result.accepted:
        span.add_event("decision.abstain_reason", {
            "reason": str(result.metadata.get("abstain_reason", "unknown")),
        })
    return span


@contextmanager
def decision_span(tracer: Tracer, spec: DecisionSpec,
                  policy: DecisionPolicy | None = None,
                  parent: Span | SpanContext | None = None,
                  extra_attributes: dict[str, Any] | None = None
                  ) -> Iterator[Span]:
    """Trace one decision: span opens before, closes after decide()."""
    attributes: dict[str, Any] = {"decision.spec_type": spec.type}
    if policy is not None:
        attributes["decision.policy_privacy_class"] = policy.privacy_class
    if extra_attributes:
        attributes.update(extra_attributes)
    with tracer.trace(DECISION_SPAN_NAME, attributes=attributes,
                      parent=parent) as span:
        yield span
