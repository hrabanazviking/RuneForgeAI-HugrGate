"""Decision explanation report. Slice 346.

Provenance (:class:`DecisionRecord
<hugrgate.provenance.DecisionRecord>`) tells you *what* was decided;
traces tell you *how long each step took*; neither tells you *why* in
one place.  :class:`DecisionExplainer` joins them into an
:class:`ExplanationReport`: a verdict summary, the policy reasoning
(threshold vs. probability, review bands, abstention reasons), the
fallback chain, the span timeline, and explicit caveats.

Privacy: the report renders the decision *value* only when
``include_value=True`` is passed explicitly — the default redacts it,
because explanation reports get pasted into tickets and dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import ObservabilityError
from hugrgate.observability.spans_decision import (
    probability_band,
)
from hugrgate.observability.trace import Span
from hugrgate.provenance import DecisionRecord
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "DecisionExplainer",
    "ExplanationReport",
]

_REDACTED = "[redacted]"


@dataclass(frozen=True)
class ExplanationReport:
    """One explained decision: structured data + markdown rendering."""

    verdict: str
    summary: str
    sections: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "summary": self.summary,
            "sections": {k: v for k, v in self.sections.items()},
        }

    def render_markdown(self) -> str:
        lines = [f"# Decision explanation — {self.verdict}", "",
                 self.summary, ""]
        for title, body in self.sections.items():
            lines.append(f"## {title}")
            lines.append("")
            if isinstance(body, dict):
                for key, value in body.items():
                    lines.append(f"- **{key}**: {value}")
            elif isinstance(body, list):
                for item in body:
                    lines.append(f"- {item}")
            else:
                lines.append(str(body))
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


class DecisionExplainer:
    """Build explanation reports from provenance + trace spans."""

    def explain(self, record: DecisionRecord,
                spans: list[Span] | None = None,
                include_value: bool = False) -> ExplanationReport:
        """Explain one recorded decision.

        *spans* are the finished spans of the decision's trace (may be
        empty).  The decision value is redacted unless *include_value*
        is passed explicitly.
        """
        if not isinstance(record, DecisionRecord):
            raise ObservabilityError(
                f"explain() needs a DecisionRecord, got "
                f"{type(record).__name__}")
        spans = list(spans or [])
        verdict = self._verdict(record)
        value = record.value if include_value else _REDACTED
        summary = self._summarize(record, verdict, value)
        sections: dict[str, Any] = {
            "What was decided": {
                "verdict": verdict,
                "value": value,
                "probability_band": probability_band(record.probability),
                "spec_type": record.spec.get("type", "unknown"),
                "backend": record.backend,
                "model": record.model,
                "latency_ms": round(record.latency_ms, 3),
            },
            "Why this verdict": self._why(record, verdict),
            "Trace timeline": [
                self._span_line(span) for span in sorted(
                    spans, key=lambda s: s.start_time)
            ] or ["(no spans recorded)"],
            "Caveats": self._caveats(record),
        }
        if record.fallback_used:
            sections["Fallback chain"] = list(record.fallback_trace) or [
                "(fallback engaged, no step detail recorded)"]
        return ExplanationReport(verdict=verdict, summary=summary,
                                 sections=sections)

    def _verdict(self, record: DecisionRecord) -> str:
        if not record.accepted:
            return "abstain"
        verdict = str(record.metadata.get("policy_verdict", "accept"))
        return verdict if verdict in ("accept", "review") else "accept"

    def _summarize(self, record: DecisionRecord, verdict: str,
                   value: Any) -> str:
        prob = probability_band(record.probability)
        if verdict == "abstain":
            reason = record.metadata.get("abstain_reason", "unknown")
            return (f"The gate abstained (reason: {reason}) instead of "
                    f"deciding — no value was returned.")
        if verdict == "review":
            return (f"The gate leaned toward {value!r} (confidence band "
                    f"{prob}) but routed the decision to human review.")
        return (f"The gate decided {value!r} with confidence band {prob} "
                f"via backend {record.backend!r} in "
                f"{record.latency_ms:.1f} ms.")

    def _why(self, record: DecisionRecord, verdict: str) -> dict[str, Any]:
        why: dict[str, Any] = {
            "policy_threshold": record.policy_threshold,
            "probability_band": probability_band(record.probability),
            "calibration_profile": record.calibration_profile,
        }
        if verdict == "abstain":
            why["abstain_reason"] = record.metadata.get("abstain_reason",
                                                        "unknown")
            why["explanation"] = (
                "The result did not satisfy the acceptance policy "
                "(probability below threshold or explicit veto), so the "
                "gate refused rather than guess.")
        elif verdict == "review":
            why["explanation"] = (
                "Confidence fell inside the policy's review band: "
                "neither strong enough to accept nor weak enough to "
                "abstain.")
        else:
            why["explanation"] = (
                f"Probability band {probability_band(record.probability)} "
                f"cleared the policy threshold "
                f"{record.policy_threshold}.")
        if record.fallback_used:
            why["fallback_used"] = True
        return why

    def _span_line(self, span: Span) -> str:
        try:
            duration_ms = span.duration_s * 1000.0
            timing = f"{duration_ms:.2f} ms"
        except Exception:  # noqa: BLE001 - unfinished spans still list
            timing = "unfinished"
        return (f"{span.name} [{span.status}] — {timing} "
                f"(trace {span.trace_id[:8]}…)")

    def _caveats(self, record: DecisionRecord) -> list[str]:
        caveats = []
        if record.calibration_profile in ("none", "unknown", ""):
            caveats.append(
                "No calibration profile: the reported confidence band is "
                "uncalibrated model output.")
        if not record.record_hash:
            caveats.append(
                "Record carries no integrity hash: provenance was not "
                "sealed for this decision.")
        if record.fallback_used:
            caveats.append(
                "A fallback path engaged: the primary backend did not "
                "produce this decision.")
        if not caveats:
            caveats.append("(none)")
        return caveats

    def explain_result(self, spec: DecisionSpec, result: DecisionResult,
                       include_value: bool = False) -> ExplanationReport:
        """Explain a live result without a provenance store round-trip."""
        record = DecisionRecord.from_decision({}, spec, result,
                                              redact_input=True)
        return self.explain(record, include_value=include_value)
