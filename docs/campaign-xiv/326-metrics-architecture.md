# Slice 326 — Metrics architecture

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_metrics.py` (22 tests), `tests/test_errors.py` (extended)

## What existed

Campaign VI's `hugrgate/adaptive/telemetry.py` kept a JSONL *event log*
for offline learning, but HugrGate had no *live* instrument surface:
no counters, gauges, or histograms, and no shared registry operators
could scrape.

## What changed

- `hugrgate/observability/` package (stdlib-only, leaf-level imports).
- `hugrgate/observability/metrics.py`: `MetricRegistry` with
  Prometheus-compatible name/label validation, fixed label sets,
  bounded label cardinality (`max_series`, default 1000 — new series
  past the cap raise `MetricError` instead of growing memory
  unboundedly), thread-safe `Counter`/`Gauge`/`Histogram`,
  bucket-interpolated percentiles, JSON-serializable `snapshot()`,
  and a `timer()` context manager.
- `hugrgate/errors.py`: Campaign XIV error taxonomy promoted up
  front — `ObservabilityError`, `MetricError`, `TraceError`,
  `SLOError`, `AlertError` with codes and deliberate recoverable
  flags (recording failures never take down a decision; bad SLO
  definitions are caller bugs).

## Verification

22 new tests (validation failures, cardinality cap, conflicting
re-registration, thread-safety, snapshot JSON); `ruff` and `mypy`
clean; error taxonomy tests extended.
