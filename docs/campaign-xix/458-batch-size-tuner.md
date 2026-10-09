# Slice 458 — Batch-size tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_458_batching.py` (8 tests)

## What existed

Batch sizes were static config. Nothing fitted the actual
fixed-cost + per-item-cost curve from measurements, so batch choice
was folklore.

## What changed

- `hugrgate/autotune/tuners/batching.py`: `BatchSizeTuner` fits
  `latency(b) = a + c·b` and `memory(b) = m0 + m1·b` by least squares
  from measured samples, then maximizes `throughput = b/latency(b)`
  over powers-of-two candidates inside the param bounds, filtered by
  latency and memory caps:
  - refuses to trust a bad model: silence when latency R² < 0.5;
  - silence when nothing is feasible;
  - evidence carries fitted coefficients, R² values, and the
    baseline-vs-tuned modeled throughput — re-derivable from the
    input samples.

## Verification

8 new tests (least-squares fit, power-of-two grid, best-feasible
selection under a latency cap, memory-cap binding, silence on noise
and on infeasibility, spec validation, end-to-end offline); `ruff`
and `mypy` clean.
