"""Slice 328 — trace architecture: spans, sampling, propagation, store."""

from __future__ import annotations

import json
import re
import threading

import pytest

from hugrgate.errors import TraceError
from hugrgate.observability.trace import (
    FORBIDDEN_ATTRIBUTE_KEYS,
    ProbabilisticSampler,
    Span,
    SpanContext,
    Tracer,
    TraceStore,
    new_span_id,
    new_trace_id,
)


def _ctx() -> SpanContext:
    return SpanContext(trace_id=new_trace_id(), span_id=new_span_id())


def test_id_formats():
    assert re.fullmatch(r"[0-9a-f]{32}", new_trace_id())
    assert re.fullmatch(r"[0-9a-f]{16}", new_span_id())


def test_span_context_rejects_bad_ids():
    with pytest.raises(TraceError):
        SpanContext(trace_id="xyz", span_id=new_span_id())
    with pytest.raises(TraceError):
        SpanContext(trace_id=new_trace_id(), span_id="xyz")


def test_span_lifecycle_and_export():
    span = Span("decide", _ctx(), attributes={"backend": "stub"})
    span.set_attribute("verdict", "accept")
    span.add_event("backend.selected", {"backend": "stub"})
    span.finish()
    assert span.finished
    assert span.duration_s >= 0.0
    doc = span.to_dict()
    json.dumps(doc)  # JSON-serializable
    assert doc["name"] == "decide"
    assert doc["attributes"]["verdict"] == "accept"
    assert doc["events"][0]["name"] == "backend.selected"
    assert doc["status"] == "ok"


def test_span_rejects_empty_name():
    with pytest.raises(TraceError):
        Span("", _ctx())


def test_forbidden_attribute_keys_raise():
    span = Span("s", _ctx())
    for key in ("state", "value", "input", "prompt", "payload", "pii"):
        assert key in FORBIDDEN_ATTRIBUTE_KEYS
        with pytest.raises(TraceError):
            span.set_attribute(key, "smuggled")
    with pytest.raises(TraceError):
        Span("s", _ctx(), attributes={"value": 1})


def test_forbidden_keys_in_events_raise():
    span = Span("s", _ctx())
    with pytest.raises(TraceError):
        span.add_event("e", {"document": "nope"})


def test_non_json_attribute_raises():
    span = Span("s", _ctx())
    with pytest.raises(TraceError):
        span.set_attribute("weird", object())


def test_oversize_attribute_raises():
    span = Span("s", _ctx())
    with pytest.raises(TraceError):
        span.set_attribute("note", "x" * 5000)


def test_mutation_after_finish_raises():
    span = Span("s", _ctx())
    span.finish()
    with pytest.raises(TraceError):
        span.set_attribute("a", "b")
    with pytest.raises(TraceError):
        span.add_event("e")
    with pytest.raises(TraceError):
        span.finish()
    with pytest.raises(TraceError):
        span.set_error("x")


def test_export_unfinished_span_raises():
    with pytest.raises(TraceError):
        Span("s", _ctx()).to_dict()


def test_end_before_start_raises():
    span = Span("s", _ctx(), start_time=100.0)
    with pytest.raises(TraceError):
        span.finish(end_time=50.0)


def test_parent_propagation():
    tracer = Tracer()
    with tracer.trace("root") as root:
        with tracer.trace("child") as child:
            assert child.trace_id == root.trace_id
            assert child.parent_span_id == root.span_id
            assert child.trace_id != child.span_id
    roots = tracer.store.find_spans("root")
    assert len(roots) == 1


def test_explicit_parent_context_continues_remote_trace():
    tracer = Tracer()
    remote = SpanContext(trace_id=new_trace_id(), span_id=new_span_id())
    with tracer.trace("child", parent=remote) as child:
        assert child.trace_id == remote.trace_id
        assert child.parent_span_id == remote.span_id


def test_tracer_records_errors_and_reraises():
    tracer = Tracer()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with tracer.trace("failing"):
            raise Boom("kaput")
    spans = tracer.store.find_spans("failing")
    assert len(spans) == 1
    assert spans[0].status.startswith("error: Boom")


def test_sampler_is_deterministic_per_trace():
    sampler = ProbabilisticSampler(rate=0.5)
    tid = new_trace_id()
    assert sampler.should_sample(tid) == sampler.should_sample(tid)


def test_sampler_boundaries():
    assert ProbabilisticSampler(rate=1.0).should_sample(new_trace_id())
    assert not ProbabilisticSampler(rate=0.0).should_sample(new_trace_id())
    with pytest.raises(TraceError):
        ProbabilisticSampler(rate=1.5)


def test_sampler_actually_splits_at_half():
    sampler = ProbabilisticSampler(rate=0.5)
    kept = sum(sampler.should_sample(new_trace_id()) for _ in range(2000))
    assert 800 < kept < 1200  # ~50% with wide tolerance


def test_unsampled_spans_are_dropped():
    tracer = Tracer(sampler=ProbabilisticSampler(rate=0.0))
    with tracer.trace("dropped") as span:
        assert span.dropped
        span.set_attribute("backend", "x")  # lifecycle still works
    assert len(tracer.store) == 0


def test_store_bounds_and_eviction():
    store = TraceStore(max_spans=5)
    for i in range(8):
        span = Span(f"s{i}", _ctx())
        span.finish()
        store.add(span)
    assert len(store) == 5
    assert [s.name for s in store.find_spans("s0")] == []
    assert len(store.find_spans("s7")) == 1


def test_store_rejects_unfinished_spans():
    store = TraceStore()
    with pytest.raises(TraceError):
        store.add(Span("s", _ctx()))


def test_get_trace_reassembles_in_time_order():
    store = TraceStore()
    tid = new_trace_id()
    spans = []
    for i in range(3):
        span = Span(f"s{i}", SpanContext(trace_id=tid, span_id=new_span_id()),
                    start_time=100.0 + (2 - i))
        span.finish()
        store.add(span)
        spans.append(span)
    ordered = store.get_trace(tid)
    assert [s.name for s in ordered] == ["s2", "s1", "s0"]
    assert store.get_trace("f" * 32) == []


def test_span_links_validate_ids():
    span = Span("s", _ctx())
    span.add_link(new_trace_id(), new_span_id())
    with pytest.raises(TraceError):
        span.add_link("bad", new_span_id())
    span.finish()
    assert len(span.to_dict()["links"]) == 1


def test_traced_decorator():
    tracer = Tracer()

    @tracer.traced("my.op")
    def op(x: int) -> int:
        return x * 2

    assert op(21) == 42
    assert len(tracer.store.find_spans("my.op")) == 1


def test_tracer_is_thread_safe():
    tracer = Tracer()

    def work() -> None:
        for _ in range(20):
            with tracer.trace("op"):
                pass

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(tracer.store.find_spans("op")) == 80
