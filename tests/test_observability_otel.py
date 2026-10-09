"""Slice 327 — OpenTelemetry integration: traceparent, bridge, exporters.

The OTel SDK is an *optional* extra; these tests run with and without
it.  SDK-present behavior is exercised through a fake SDK injected via
``sys.modules`` so the suite never needs the real package installed.
"""

from __future__ import annotations

import types

import pytest

from hugrgate.errors import ObservabilityError, TraceError
from hugrgate.observability import otel
from hugrgate.observability.otel import (
    InMemoryExporter,
    OtelBridge,
    OtelConfig,
    decode_traceparent,
    encode_traceparent,
)
from hugrgate.observability.trace import (
    Span,
    SpanContext,
    new_span_id,
    new_trace_id,
)


def _finished_span(name: str = "op") -> Span:
    span = Span(name, SpanContext(trace_id=new_trace_id(),
                                 span_id=new_span_id()),
                attributes={"backend": "stub"})
    span.add_event("e", {"k": "v"})
    span.finish()
    return span


# --- traceparent ------------------------------------------------------------


def test_traceparent_round_trip():
    tid, sid = new_trace_id(), new_span_id()
    header = encode_traceparent(tid, sid, sampled=True)
    assert header == f"00-{tid}-{sid}-01"
    parsed = decode_traceparent(header)
    assert parsed == {"trace_id": tid, "span_id": sid, "sampled": True}
    assert decode_traceparent(encode_traceparent(tid, sid, sampled=False))[
        "sampled"] is False


def test_traceparent_rejects_malformed():
    for bad in ("", "00-short", "00-" + "a" * 32 + "-" + "b" * 16,
                "ff-" + "a" * 32 + "-" + "b" * 16 + "-01",
                "00-" + "0" * 32 + "-" + "b" * 16 + "-01",
                "00-" + "a" * 32 + "-" + "0" * 16 + "-01"):
        with pytest.raises(TraceError):
            decode_traceparent(bad)


def test_encode_traceparent_validates_ids():
    with pytest.raises(TraceError):
        encode_traceparent("nope", new_span_id())
    with pytest.raises(TraceError):
        encode_traceparent(new_trace_id(), "nope")


# --- config -----------------------------------------------------------------


def test_otel_config_validation():
    with pytest.raises(TraceError):
        OtelConfig(service_name="")
    with pytest.raises(TraceError):
        OtelConfig(sample_rate=2.0)
    with pytest.raises(TraceError):
        OtelConfig(endpoint="not-a-url")


# --- fallback exporter ------------------------------------------------------


def test_in_memory_exporter_bounds():
    exporter = InMemoryExporter(max_spans=3)
    exporter.export([_finished_span(f"s{i}") for i in range(5)])
    assert [s.name for s in exporter.spans] == ["s2", "s3", "s4"]
    exporter.clear()
    assert exporter.spans == []
    with pytest.raises(TraceError):
        InMemoryExporter(max_spans=0)


# --- bridge without SDK -----------------------------------------------------


def test_bridge_degrades_without_sdk(monkeypatch):
    monkeypatch.setattr(otel, "_load_sdk", lambda: None)
    fallback = InMemoryExporter()
    bridge = OtelBridge(fallback=fallback)
    assert bridge.configure() is False
    assert bridge.sdk_available is False
    span = _finished_span()
    bridge.export([span])
    assert fallback.spans == [span]  # local-first: nothing lost
    with pytest.raises(ObservabilityError, match="otel"):
        bridge.require_sdk()


def test_bridge_disabled_config_never_touches_sdk(monkeypatch):
    def _boom() -> None:
        raise AssertionError("SDK must not load when disabled")

    monkeypatch.setattr(otel, "_load_sdk", _boom)
    bridge = OtelBridge(config=OtelConfig(enabled=False))
    assert bridge.configure() is False


# --- bridge with a fake SDK -------------------------------------------------


def _install_fake_sdk(monkeypatch):
    """Inject fake OTel API + SDK modules through the seams in otel.py.

    Patching ``otel._otel_trace`` (not ``sys.modules``): once the real
    ``opentelemetry.trace`` has been imported anywhere in the process
    (e.g. by FastAPI's optional instrumentation), ``import a.b as c``
    resolves through the parent package attribute and a
    ``sys.modules`` fake is silently ignored.
    """
    recorded: list[dict] = []

    fake_trace = types.ModuleType("opentelemetry.trace")

    class TraceFlags(int):
        pass

    class SpanKind:
        INTERNAL = "internal"

    class StatusCode:
        ERROR = "error"

    class Status:
        # Mirrors the real API: Status(status_code, description).
        def __init__(self, status_code, description=None):
            self.status_code = status_code
            self.description = description

    class SpanContext:
        def __init__(self, trace_id, span_id, is_remote, trace_flags):
            self.trace_id = trace_id
            self.span_id = span_id

    class NonRecordingSpan:
        def __init__(self, ctx):
            self.ctx = ctx

    def set_span_in_context(span):
        return {"span": span}

    fake_trace.TraceFlags = TraceFlags
    fake_trace.SpanKind = SpanKind
    fake_trace.StatusCode = StatusCode
    fake_trace.Status = Status
    fake_trace.SpanContext = SpanContext
    fake_trace.NonRecordingSpan = NonRecordingSpan
    fake_trace.set_span_in_context = set_span_in_context

    class FakeSDKSpan:
        def __init__(self, name, **kwargs):
            self.name = name
            self.kwargs = kwargs
            self.events = []
            self.status = None
            self.ended = False

        def add_event(self, name, attributes=None, timestamp=None):
            self.events.append((name, attributes))

        def set_status(self, status):
            self.status = status

        def end(self, end_time=None):
            self.ended = True
            recorded.append({
                "name": self.name,
                "attributes": self.kwargs.get("attributes"),
                "events": self.events,
                "status": self.status,
                "ended": self.ended,
            })

    class FakeTracer:
        def start_span(self, name, **kwargs):
            return FakeSDKSpan(name, **kwargs)

    class FakeProvider:
        def get_tracer(self, *args, **kwargs):
            return FakeTracer()

        def force_flush(self, timeout_millis=None):
            pass

        def shutdown(self):
            pass

    fake_sdk = types.ModuleType("opentelemetry.sdk.trace")
    fake_sdk.TracerProvider = FakeProvider

    monkeypatch.setattr(otel, "_load_sdk", lambda: fake_sdk)
    monkeypatch.setattr(otel, "_otel_trace", lambda: fake_trace)
    return recorded


def test_bridge_exports_via_sdk_and_fallback(monkeypatch):
    recorded = _install_fake_sdk(monkeypatch)
    fallback = InMemoryExporter()
    bridge = OtelBridge(fallback=fallback)
    assert bridge.configure() is True
    assert bridge.sdk_available is True
    span = _finished_span("decision")
    bridge.export([span])
    assert len(recorded) == 1
    assert recorded[0]["name"] == "decision"
    assert recorded[0]["attributes"]["backend"] == "stub"
    assert recorded[0]["events"][0][0] == "e"
    assert recorded[0]["ended"] is True
    # local-first: the fallback still got the span
    assert fallback.spans == [span]
    bridge.shutdown()


def test_bridge_converts_error_status(monkeypatch):
    recorded = _install_fake_sdk(monkeypatch)
    bridge = OtelBridge()
    bridge.configure()
    span = _finished_span("bad")
    # NOTE: _finished_span already finished; build the error span directly
    ctx = SpanContext(trace_id=new_trace_id(), span_id=new_span_id())
    span = Span("bad", ctx, attributes={"backend": "stub"})
    span.set_error("kaput")
    span.finish()
    bridge.export([span])
    assert recorded[0]["status"].status_code == "error"
    bridge.shutdown()
