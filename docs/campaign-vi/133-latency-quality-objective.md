# Slice 133 — Latency-quality objective

**Status:** complete. **Tests:** `tests/test_adaptive_latency_quality.py` — 8 tests green.

## What existed before

`CostQualityObjective` (slice 132) covered money; latency had no objective
and no measurement discipline.

## What was built

`hugrgate/adaptive/latency_quality.py`:

- `LatencyQualityObjective`: `score = w_q·quality − w_l·(latency_ms/latency_scale)`.
- `measure_latency(fn, n_runs, label)`: times a callable, returns a
  `LatencyMeasurement` (n, mean, p50, p95, min, max) — computed, never
  invented.
- `compare_to_baseline(measurement, baseline_mean_ms, baseline_label)`:
  delta/ratio/faster-than-baseline from two real numbers. Every latency
  claim in Campaign VI (including the slice-149 benchmark) can cite one of
  these artifacts.

## Integration

- Implements slice-132's `RouteObjective`; `SpecError` on bad weights/scale,
  non-positive baselines, `n_runs < 1`.

## Verification

- `pytest tests/test_adaptive_latency_quality.py` — 8/8 green: faster
  wins at equal quality, quality/latency trade-off math, a real 1ms-sleep
  measurement artifact (mean ≥ 0.5ms — actually measured), baseline
  comparison deltas/ratios both directions.
- `mypy hugrgate/adaptive` — clean.
