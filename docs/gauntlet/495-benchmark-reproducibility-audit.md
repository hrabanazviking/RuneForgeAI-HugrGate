# Slice 495 — Benchmark reproducibility audit

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_495_repro.py` (9 tests)

## What it does

`hugrgate/gauntlet/repro.py` — a benchmark harness that audits
itself:

- `run_workload(n, seed)` — deterministic decision workload
  (seeded states, fixed stub backend, explicit slice-492 batch
  limits); returns a SHA-256 digest of all results plus timing.
- `run_reproducibility_audit(runs)` — asserts **exact** digest
  identity across runs (determinism) and timing coefficient of
  variation ≤ 0.25 (noise band — timing is honestly noisy).
- `compare_with_baseline()` — compares a fresh measurement
  against a recorded baseline JSON: digest mismatch is always a
  failure; ops/sec drift > 30% flags human review.

## Measured artifact (real numbers, this machine)

`docs/gauntlet/495-benchmark-baseline.json` — 3 runs × 2000
decisions, seed 495:

- digests identical across runs: `5992c1a0b43a…`
- ops/sec: 7830.8 / 8977.0 / 9173.8 (CV 0.068 — within band)
- baseline comparison: within band, drift 0.146

No numbers invented; rerun `run_reproducibility_audit()` to
re-measure on any machine.

## Verification

9 tests green; `ruff`/`mypy` clean.
