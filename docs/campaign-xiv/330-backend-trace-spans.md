# Slice 330 — Backend trace spans

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_spans.py`

## What existed

Backend invocations were timed inside health stats but had no span
representation; retry attempts were invisible as separate operations.

## What changed

- `hugrgate/observability/spans_backend.py`: `backend_span()`
  context manager — one child span per attempt (attempt number as
  attribute), wall-clock latency measured by the span itself,
  taxonomy error codes recorded on failure, exceptions re-raised so
  retry semantics are untouched.
- `hugrgate/observability/trace.py` (hardening): `Tracer.trace` now
  applies **first-error-wins** — a nested builder's specific error
  code is no longer overwritten by the outer generic handler.

## Verification

Covered in `tests/test_observability_spans.py` (success latency,
taxonomy-code recording, stdlib-error type names, attempt
validation); `ruff`/`mypy` clean.
