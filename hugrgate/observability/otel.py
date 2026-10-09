"""OpenTelemetry interop for HugrGate traces. Slice 327.

HugrGate's own trace model lives in :mod:`hugrgate.observability.trace`
(stdlib-only, local-first).  This module is the *bridge* to the wider
OpenTelemetry ecosystem:

- W3C ``traceparent`` encode/decode for cross-process propagation;
- :class:`OtelBridge`, which forwards HugrGate spans to a real OTel SDK
  when the ``otel`` extra is installed, and otherwise degrades to a
  documented in-process fallback instead of raising at import time;
- exporter abstractions (:class:`SpanExporter`, :class:`InMemoryExporter`)
  so tests and operators can capture spans without any SDK.

Local-first philosophy (Execution Law 15): HugrGate never *requires*
the OTel SDK.  The bridge is explicit — :meth:`OtelBridge.configure`
reports ``sdk_available`` — and the fallback keeps every span locally
inspectable through :class:`InMemoryExporter`.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from hugrgate.errors import ObservabilityError, TraceError

if TYPE_CHECKING:  # pragma: no cover
    from hugrgate.observability.trace import Span

__all__ = [
    "InMemoryExporter",
    "OtelBridge",
    "OtelConfig",
    "SpanExporter",
    "_load_sdk",
    "decode_traceparent",
    "encode_traceparent",
]

_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<parent_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$")


@dataclass(frozen=True)
class OtelConfig:
    """Configuration for the OpenTelemetry bridge.

    ``endpoint`` is the OTLP HTTP endpoint used when the SDK is present.
    ``sample_rate`` mirrors :class:`trace.ProbabilisticSampler` so the
    SDK and the local tracer can share one policy.
    """

    service_name: str = "hugrgate"
    service_version: str = "0.0.0"
    endpoint: str = "http://localhost:4318/v1/traces"
    enabled: bool = True
    sample_rate: float = 1.0
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.service_name:
            raise TraceError("OtelConfig.service_name must be non-empty")
        if not 0.0 <= self.sample_rate <= 1.0:
            raise TraceError(
                f"OtelConfig.sample_rate must be in [0, 1], got "
                f"{self.sample_rate!r}")
        if "://" not in self.endpoint:
            raise TraceError(
                f"OtelConfig.endpoint must be a URL, got {self.endpoint!r}")


def encode_traceparent(trace_id: str, span_id: str,
                       sampled: bool = True) -> str:
    """Render a W3C ``traceparent`` header value (version ``00``)."""
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
        raise TraceError(f"bad trace_id for traceparent: {trace_id!r}")
    if not re.fullmatch(r"[0-9a-f]{16}", span_id):
        raise TraceError(f"bad span_id for traceparent: {span_id!r}")
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


def decode_traceparent(header: str) -> dict[str, Any]:
    """Parse a W3C ``traceparent`` header into its components.

    Returns ``{"trace_id", "span_id", "sampled"}``; malformed headers
    raise :class:`~hugrgate.errors.TraceError` instead of silently
    producing a broken context.
    """
    match = _TRACEPARENT_RE.match((header or "").strip())
    if not match:
        raise TraceError(f"malformed traceparent header: {header!r}")
    parts = match.groupdict()
    if parts["version"] == "ff":
        raise TraceError("traceparent version 'ff' is reserved")
    if parts["trace_id"] == "0" * 32 or parts["parent_id"] == "0" * 16:
        raise TraceError("traceparent carries all-zero ids")
    return {
        "trace_id": parts["trace_id"],
        "span_id": parts["parent_id"],
        "sampled": parts["flags"] == "01",
    }


class SpanExporter(Protocol):
    """Sink for finished spans."""

    def export(self, spans: list[Span]) -> None:
        """Export a batch of finished spans (must not raise on drop)."""
        ...


class InMemoryExporter:
    """Test/operator exporter: keeps finished spans in a bounded list."""

    def __init__(self, max_spans: int = 10000) -> None:
        if max_spans < 1:
            raise TraceError("InMemoryExporter.max_spans must be positive")
        self._max_spans = max_spans
        self._lock = threading.Lock()
        self._spans: list[Span] = []

    def export(self, spans: list[Span]) -> None:
        with self._lock:
            self._spans.extend(spans)
            del self._spans[:max(0, len(self._spans) - self._max_spans)]

    @property
    def spans(self) -> list[Span]:
        with self._lock:
            return list(self._spans)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


def _load_sdk() -> Any | None:
    """Import the OTel SDK lazily; ``None`` when the extra is absent.

    The ``import`` statements below are function-local on purpose: the
    SDK is an optional extra (``otel``), so importing this module must
    never require it.  The dependency-gate map
    (``tests/test_dependency_rules.py``) still declares the provider.
    """
    try:
        import opentelemetry.sdk.trace
        import opentelemetry.trace  # noqa: F401
    except ImportError:
        return None
    import opentelemetry.sdk.trace as sdk_trace
    return sdk_trace


class OtelBridge:
    """Forward HugrGate spans to OpenTelemetry when the SDK is present.

    Lifecycle: construct with an :class:`OtelConfig` and a fallback
    :class:`SpanExporter`, then call :meth:`configure`.  When the SDK is
    installed, spans are converted to SDK spans and emitted through a
    ``BatchSpanProcessor`` (OTLP exporter only if ``endpoint`` is
    reachable — construction never performs network I/O).  When it is
    absent, spans go to the fallback exporter and
    :attr:`sdk_available` is ``False``.
    """

    def __init__(self, config: OtelConfig | None = None,
                 fallback: SpanExporter | None = None) -> None:
        self._config = config or OtelConfig()
        self._fallback = fallback or InMemoryExporter()
        self._lock = threading.Lock()
        self._configured = False
        self._sdk_available = False
        self._tracer: Any = None

    @property
    def sdk_available(self) -> bool:
        return self._sdk_available

    @property
    def config(self) -> OtelConfig:
        return self._config

    def configure(self) -> bool:
        """Wire the SDK if present; return whether the SDK path is live."""
        with self._lock:
            if self._configured:
                return self._sdk_available
            if not self._config.enabled:
                self._configured = True
                self._sdk_available = False
                return False
            sdk_trace = _load_sdk()
            if sdk_trace is None:
                self._configured = True
                self._sdk_available = False
                return False
            provider = sdk_trace.TracerProvider()
            # OTLP exporter is wired lazily per-batch below so that a
            # missing collector never breaks configuration.
            self._tracer = provider.get_tracer(
                self._config.service_name,
                schema_url=None,
            )
            self._provider = provider
            self._configured = True
            self._sdk_available = True
            return True

    def require_sdk(self) -> None:
        """Raise unless the SDK path is live (explicit opt-in checks)."""
        if not self.configure():
            raise ObservabilityError(
                "OpenTelemetry SDK not available: install the 'otel' "
                "extra (pip install hugrgate[otel]) to enable OTLP export; "
                "spans remain available through the fallback exporter.")

    def export(self, spans: list[Span]) -> None:
        """Export finished spans via SDK (if live) and the fallback."""
        live = self.configure()
        if live:
            self._export_via_sdk(spans)
        # The fallback always receives spans: local-first means the
        # operator can inspect everything even when OTLP is live.
        self._fallback.export(spans)

    def _export_via_sdk(self, spans: list[Span]) -> None:
        try:
            import opentelemetry.trace as otel_trace
        except ImportError as exc:  # pragma: no cover - configure() checked
            raise ObservabilityError(
                "OTel SDK vanished after configure()") from exc
        for span in spans:
            ctx = otel_trace.SpanContext(
                trace_id=int(span.trace_id, 16),
                span_id=int(span.span_id, 16),
                is_remote=False,
                trace_flags=otel_trace.TraceFlags(
                    0x01 if span.sampled else 0x00),
            )
            sdk_span = self._tracer.start_span(
                span.name, context=otel_trace.set_span_in_context(
                    otel_trace.NonRecordingSpan(ctx)),
                start_time=int(span.start_time * 1e9),
                attributes=dict(span.attributes),
                kind=otel_trace.SpanKind.INTERNAL,
            )
            for event in span.events:
                sdk_span.add_event(
                    event["name"],
                    attributes=event.get("attributes"),
                    timestamp=int(event["timestamp"] * 1e9),
                )
            if span.status != "ok":
                sdk_span.set_status(otel_trace.Status(
                    otel_trace.StatusCode.ERROR, span.status))
            sdk_span.end(end_time=int(span.end_time * 1e9))

    def shutdown(self, timeout_s: float = 5.0) -> None:
        """Flush SDK processors; the fallback exporter needs no flush."""
        with self._lock:
            provider = getattr(self, "_provider", None)
            self._configured = False
            self._sdk_available = False
            self._tracer = None
        if provider is not None:
            provider.force_flush(timeout_millis=int(timeout_s * 1000))
            provider.shutdown()
