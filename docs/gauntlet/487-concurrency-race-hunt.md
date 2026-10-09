# Slice 487 — Concurrency race hunt

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_487_racehunt.py` (7 tests)

## What existed

Thread-safety was audited (slices 017/293) but no reusable
contention harness existed to keep it honest.

## What changed

- `hugrgate/gauntlet/racehunt.py` (new): `hammer()` — N threads
  rendezvous on a barrier (real contention), exceptions captured
  with tracebacks, deadlocks detected via join timeouts, and a
  caller-supplied invariant as the actual race detector;
  `hammer_cache()` (DecisionCache put/get/invalidate —
  invariant: `hits + misses == get_calls`, size ≤ max) and
  `hammer_registry()` (BackendRegistry — invariant: no duplicate
  names, every name resolves).

## Attack findings

Both production targets survive 8×200 hammering with zero
errors. The harness itself is proven against a deliberately racy
barrier-synchronized counter (deterministic lost updates → hunt
fails) and a locked counter (hunt passes).

## Verification

`pytest tests/test_gauntlet_487_racehunt.py` green (7 tests, stable
across 3 runs); `ruff`/`mypy` clean.
