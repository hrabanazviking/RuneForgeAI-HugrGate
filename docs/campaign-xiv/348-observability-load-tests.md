# Slice 348 — Observability load tests

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_load.py` (4 tests)

## What existed

No measurement of what the observability layer itself costs — the
campaign could have shipped a watcher heavier than the watched.

## What changed

- `hugrgate/observability/load.py`: `ObservabilityLoadHarness` runs
  N fully-instrumented decision iterations (tracer + decision/backend
  spans + dashboard observation) against a bare baseline and reports
  p50/p99/max plus p99 overhead; `assert_within_budget()` is the gate
  (raises `ObservabilityError` over budget). The harness
  self-verifies: it asserts the dashboard recorded every iteration,
  so a silently-broken instrumented path cannot produce a passing
  "zero overhead" result.

## Verification

4 tests (real overhead measured and inside the 500 µs gate budget,
gate trips on an impossible budget, input validation); `ruff`/`mypy`
clean.
