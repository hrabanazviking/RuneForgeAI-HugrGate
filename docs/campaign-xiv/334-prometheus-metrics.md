# Slice 334 — Prometheus metrics

**Date:** 2026-10-09 · **Tests:** `tests/test_observability_prometheus.py` (9 tests)

## What existed

The metric registry (slice 326) had a `snapshot()` but no exporter —
Prometheus could not scrape HugrGate.

## What changed

- `hugrgate/observability/prometheus.py`: `generate_latest()`
  renders the registry in Prometheus text format 0.0.4 —
  counters as `<name>_total`, gauges plain, histograms as cumulative
  `le` buckets plus implicit `+Inf`, `_sum`, `_count`;
  spec-compliant label escaping; NaN series refused loudly rather
  than emitted. Reads only `snapshot()`, never instrument internals.

## Verification

9 tests (suffixing, bucket cumulativity, escaping of quotes/newlines/
backslashes, NaN refusal); `ruff`/`mypy` clean.
