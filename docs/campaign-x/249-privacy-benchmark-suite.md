# Slice 249 — Privacy benchmark suite

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_bench_249.py` (5 tests)

## What existed

No measurements of what the privacy fortress costs: every
pipeline stage was assumed cheap, with no evidence.

## What changed

- New `benchmarks/privacy_bench_249.py` with importable
  `run_benchmark(seed=, rounds=)` measuring real per-op
  latencies (mean/p50/p95/min/max) for 10 operations:
  secret scan, PII scrub, redaction, local-only enforcement,
  full payload compile, seal, unseal, tokenize, audit record,
  dry-run. Writes `benchmarks/privacy_bench_249.json`.
- Full artifact generated (100 rounds, this machine):
  payload compile ~2.5ms mean (dominates, as expected —
  eight stages), dry-run ~2.5ms, unseal ~0.7ms, everything
  else sub-millisecond.
- `tests/test_privacy_bench_249.py`: reduced-round real
  measurements, artifact shape, sanity invariant (full
  pipeline ≥ its secret-scan stage), tmp-path artifact write.

## Verification

- `pytest tests/test_privacy_bench_249.py` — 5 passed.
- `ruff` clean (bench script and test).
