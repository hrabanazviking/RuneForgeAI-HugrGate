# Slice 327 — OpenTelemetry integration

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_otel.py` (13 tests)

## What existed

HugrGate traces (slice 328) were local-only with no path to the wider
observability ecosystem and no W3C propagation story.

## What changed

- `hugrgate/observability/otel.py`: W3C `traceparent` encode/decode
  (malformed headers raise `TraceError`), `OtelConfig` validation,
  `OtelBridge` which forwards spans to a real OTel SDK when the new
  optional `otel` extra is installed and otherwise degrades to a
  documented in-process fallback — importing the module never requires
  the SDK. The fallback *always* receives spans (local-first: the
  operator can inspect everything even when OTLP is live).
- `SpanExporter` protocol + bounded `InMemoryExporter` for tests.
- `pyproject.toml`: new `otel` extra
  (`opentelemetry-api/sdk/exporter-otlp`); `tests/test_dependency_rules.py`
  provider map + distribution normalization extended.

## Verification

13 tests, including the SDK-live export path exercised through a fake
SDK injected via `sys.modules` (suite never needs the real package);
`ruff`/`mypy` clean; dependency-gate tests green.
