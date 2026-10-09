# Slice 492 — Resource exhaustion gauntlet

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_492_exhaustion.py` (5 tests)

## What existed

Input limits existed (`hugrgate/security/input_limits.py`) but
`HugrGate.decide_batch` never called `check_batch` — an unbounded
batch fanned out with no amplification guard.

## What changed

- `hugrgate/core.py`: `decide_batch` now enforces
  `check_batch(states, limits)` before any decision runs (lazy
  import, per the codebase's cycle-avoidance pattern); new
  optional `limits: InputLimits | None` parameter; breaches raise
  `InputTooLarge`. Backward compatible: the new parameter is
  defaulted.
- `hugrgate/gauntlet/exhaustion.py` (new):
  `run_exhaustion_gauntlet()` — oversized/over-deep/non-serializable
  states, oversized batches (count and bytes), plus control and
  still-alive probes.

## Verification

`pytest` green — every exhaustion scenario contained with the
right error kind, control batch passes, gate alive after the
battery; `ruff`/`mypy` clean.
