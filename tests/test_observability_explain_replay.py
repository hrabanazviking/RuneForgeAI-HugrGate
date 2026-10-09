"""Slices 346-347 — decision explanation report + trace replay data."""

from __future__ import annotations

import json

import pytest

from hugrgate.abstain import abstain
from hugrgate.errors import ObservabilityError, TraceError
from hugrgate.observability.explain import DecisionExplainer
from hugrgate.observability.replay import TraceReplay
from hugrgate.observability.spans_backend import backend_span
from hugrgate.observability.spans_decision import (
    annotate_decision,
    decision_span,
)
from hugrgate.observability.trace import Tracer
from hugrgate.provenance import DecisionRecord
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


def _record(**over) -> DecisionRecord:
    result = DecisionResult(
        value="yes", probability=0.93,
        distribution={"yes": 0.93, "no": 0.07},
        backend="stub", model="m", latency_ms=12.5,
        calibration_profile="conformal-0.9",
        **over)
    record = DecisionRecord.from_decision({"q": 1}, _spec(), result,
                                          policy_threshold=0.8)
    return record


def _traced_decision() -> tuple[Tracer, str]:
    tracer = Tracer()
    with tracer.trace("root"):
        with decision_span(tracer, _spec()) as dspan:
            annotate_decision(dspan, _spec(), DecisionResult(
                value="yes", probability=0.93,
                distribution={"yes": 0.93, "no": 0.07}, backend="stub"))
            with backend_span(tracer, "stub", attempt=1,
                              parent=dspan):
                pass
    trace_id = tracer.store.find_spans("root")[0].trace_id
    return tracer, trace_id


# --- slice 346: explanation report ------------------------------------------------------


def test_explain_accept_path():
    explainer = DecisionExplainer()
    report = explainer.explain(_record())
    assert report.verdict == "accept"
    assert "stub" in report.summary
    assert report.sections["What was decided"]["probability_band"] == \
        "0.9-1.0"
    assert report.sections["What was decided"]["value"] == "[redacted]"
    assert "threshold" in report.sections["Why this verdict"][
        "explanation"].lower() or "cleared" in \
        report.sections["Why this verdict"]["explanation"]
    markdown = report.render_markdown()
    assert markdown.startswith("# Decision explanation — accept")
    assert "## Caveats" in markdown
    json.dumps(report.to_dict())


def test_explain_redacts_value_by_default():
    explainer = DecisionExplainer()
    default = explainer.explain(_record())
    assert default.sections["What was decided"]["value"] == "[redacted]"
    explicit = explainer.explain(_record(), include_value=True)
    assert explicit.sections["What was decided"]["value"] == "yes"


def test_explain_abstain_path():
    explainer = DecisionExplainer()
    result = abstain(_spec(), reason="below_threshold", backend="stub")
    record = DecisionRecord.from_decision({}, _spec(), result)
    report = explainer.explain(record)
    assert report.verdict == "abstain"
    assert "below_threshold" in report.summary
    assert report.sections["Why this verdict"]["abstain_reason"] == \
        "below_threshold"


def test_explain_review_path():
    explainer = DecisionExplainer()
    record = _record(metadata={"policy_verdict": "review"})
    report = explainer.explain(record)
    assert report.verdict == "review"
    assert "human review" in report.summary


def test_explain_includes_span_timeline():
    tracer, _ = _traced_decision()
    spans = tracer.store.find_spans("hugrgate.decision")
    report = DecisionExplainer().explain(_record(), spans=spans)
    timeline = report.sections["Trace timeline"]
    assert len(timeline) == 1
    assert "hugrgate.decision" in timeline[0]


def test_explain_fallback_chain_and_caveats():
    explainer = DecisionExplainer()
    record = _record(fallback_used=True)
    record.fallback_trace.append("stub -> safe_default")
    report = explainer.explain(record)
    assert "Fallback chain" in report.sections
    caveats = " ".join(report.sections["Caveats"])
    assert "fallback" in caveats.lower()


def test_explain_rejects_non_records():
    with pytest.raises(ObservabilityError):
        DecisionExplainer().explain("not-a-record")  # type: ignore[arg-type]


def test_explain_result_live_path():
    explainer = DecisionExplainer()
    result = DecisionResult(value="no", probability=0.62,
                            distribution={"yes": 0.38, "no": 0.62},
                            backend="stub",
                            metadata={"policy_verdict": "review"})
    report = explainer.explain_result(_spec(), result, include_value=True)
    assert report.verdict == "review"
    assert report.sections["What was decided"]["value"] == "no"


# --- slice 347: trace replay -----------------------------------------------------------------


def test_replay_timeline_nesting_and_order():
    tracer, trace_id = _traced_decision()
    replay = TraceReplay(tracer.store)
    timeline = replay.timeline(trace_id)
    names = [e["name"] for e in timeline]
    assert names[0] == "root"
    assert "hugrgate.decision" in names
    assert "hugrgate.backend" in names
    by_name = {e["name"]: e for e in timeline}
    assert by_name["root"]["depth"] == 0
    assert by_name["hugrgate.decision"]["depth"] == 1
    assert by_name["hugrgate.backend"]["depth"] == 2
    assert by_name["root"]["start_offset_ms"] == 0.0
    assert all(e["duration_ms"] >= 0.0 for e in timeline)
    assert not any(e["orphan"] for e in timeline)


def test_replay_document_shape():
    tracer, trace_id = _traced_decision()
    doc = TraceReplay(tracer.store).to_dict(trace_id)
    assert doc["trace_id"] == trace_id
    assert doc["span_count"] == 3
    assert doc["error_count"] == 0
    assert doc["total_duration_ms"] >= 0.0
    json.dumps(doc)


def test_replay_marks_errors():
    tracer = Tracer()
    with tracer.trace("root2") as span:
        span.set_error("boom")
    trace_id = tracer.store.find_spans("root2")[0].trace_id
    doc = TraceReplay(tracer.store).to_dict(trace_id)
    assert doc["error_count"] == 1
    text = TraceReplay(tracer.store).render_text(trace_id)
    assert "!" in text  # error marker in the waterfall


def test_replay_unknown_trace_raises():
    replay = TraceReplay(Tracer().store)
    with pytest.raises(TraceError):
        replay.timeline("f" * 32)


def test_replay_render_text_waterfall():
    tracer, trace_id = _traced_decision()
    text = TraceReplay(tracer.store).render_text(trace_id)
    assert f"trace {trace_id}" in text
    assert "hugrgate.backend" in text
    # backend span is nested two deep -> indented
    backend_line = next(line for line in text.splitlines()
                        if "hugrgate.backend" in line)
    assert backend_line.startswith("     ")


def test_replay_orphan_spans_are_kept_and_flagged():
    from hugrgate.observability.trace import (
        Span,
        SpanContext,
        new_span_id,
        new_trace_id,
    )
    store = Tracer().store
    tid = new_trace_id()
    orphan = Span("orphan", SpanContext(trace_id=tid, span_id=new_span_id()),
                  parent_span_id="d" * 16)  # parent never recorded
    orphan.finish()
    store.add(orphan)
    timeline = TraceReplay(store).timeline(tid)
    assert len(timeline) == 1
    assert timeline[0]["orphan"] is True
    assert timeline[0]["depth"] == 0
