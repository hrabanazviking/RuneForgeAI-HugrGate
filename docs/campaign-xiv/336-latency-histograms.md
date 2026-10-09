# Slice 336 — Latency histograms

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_histograms.py`

## What existed

Latency lived in `HealthMonitor` rolling windows; no dedicated
histogram instrument with percentile summaries, and no measured
statement of what instrumentation itself costs.

## What changed

- `hugrgate/observability/histograms.py`: `LatencyTracker` —
  per-backend latency histogram with ms-facing helpers,
  p50/p90/p99 summary, and an SLA predicate. Bucket-interpolated
  percentiles are documented as estimates that always lie inside a
  real bucket.
- `benchmarks/observability_overhead_336.py` →
  `benchmarks/observability_overhead_336.json`: **real measured
  overhead** of the instrumented observe path on this host —
  p50 6.3 µs, p99 14.2 µs, max 531.6 µs (n=20000, seed=336) —
  against the explicit 50 µs p99 baseline: **within baseline**.
  The artifact records its own seed, n, and host; nothing invented.

## Verification

Histogram tests + artifact-honesty tests (real numbers, baseline
comparison); `ruff`/`mypy` clean.
