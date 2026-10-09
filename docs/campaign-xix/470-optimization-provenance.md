# Slice 470 — Optimization provenance

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_470_provenance.py` (9 tests)

## What existed

Tuning runs left no audit trail: no record of who proposed what,
from which data, with what result. The decision-path provenance
(`hugrgate/provenance.py`) had a hash-chained integrity pattern the
optimizer did not reuse.

## What changed

- `hugrgate/autotune/provenance.py`:
  - `OptimizationRecord`: tuner, proposal, mode/disposition,
    changes, config hash before/after, data fingerprint, seed,
    evidence summary — sealed into the same hash-chain pattern as
    decision provenance (`prev_hash`/`record_hash`, `verify()`);
  - `OptimizationProvenance`: append-only store with
    `verify_chain()`, `by_proposal`/`by_tuner`/`recent` queries,
    JSON export, optional max-records bound;
  - `ProvenanceTracker.track_run()`: consumes a controller
    `TuningRun` directly (one call per cycle), including a
    heartbeat record for proposal-less cycles; `verify()` raises
    `ReproducibilityError` on tampering;
  - secret-looking keys redacted before recording (and the sealed
    hash commits to the redacted form).

## Verification

9 new tests (hash stability, tamper/reorder detection,
self-verification, queries, bound tradeoff documented honestly,
redaction, controller-run tracking, empty-run heartbeat,
verify-raises); `ruff` and `mypy` clean.
