# Slice 333 — Structured log schema

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_logschema.py` (11 tests)

## What existed

`hugrgate/log.py` (slice 009) gave JSON *formatting* and a
"metadata, never payload" rule, but no *schema*: operators grepped
free text, and nothing validated event fields or versions.

## What changed

- `hugrgate/observability/logschema.py`:
  - `EVENT_SCHEMAS` — versioned, append-only schemas for nine
    observability events (decision/backend/routing/calibration/
    privacy/alert/SLO/drift). New optional fields may be added;
    required fields are never removed or renamed (enforced by test).
  - `validate_event()` / `emit_event()` — validate-then-log; the
    trace payload denylist is enforced here too (a field named
    `value` or `state` raises `ObservabilityError` instead of leaking
    into logs).
  - `ObservabilityFormatter` — extends `JsonFormatter` with `event`,
    `event_version`, `fields`, `trace_id`, `span_id`.
  - `TraceLoggerAdapter` — stamps every record with ambient
    trace/span ids.

## Verification

11 tests (schema append-only invariant, payload rejection, JSON
round-trip, adapter stamping); `ruff`/`mypy` clean.
