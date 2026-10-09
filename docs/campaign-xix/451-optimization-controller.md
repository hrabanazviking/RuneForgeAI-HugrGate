# Slice 451 — Optimization controller

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_451_controller.py` (22 tests)

## What existed

HugrGate had per-component knobs everywhere (threshold gates in
`hugrgate/threshold.py`, cache TTL/size in `hugrgate/cache.py`, bandit
exploration rates in `hugrgate/adaptive/`) but no *optimizer*: nothing
could propose, validate, and safely apply changes to those knobs.
There was no typed registry of what is tunable, no proposal lifecycle,
and no mode discipline (offline vs live).

## What changed

- `hugrgate/errors.py`: Campaign XIX error taxonomy up front —
  `AutotuneError` (base, recoverable: a failed tuning cycle must never
  take down the decision path), `ObjectiveError` / `ParameterError`
  (caller bugs, not recoverable), `ConstraintViolation` (recoverable:
  proposal skipped), `TunerError` (recoverable: tuner skipped),
  `UnsafeProposalError` / `RollbackError` / `ReproducibilityError`
  (not recoverable: policy/state-integrity problems).
- `hugrgate/autotune/` package (new) with `controller.py`:
  - `TunableParameter`: typed knob (float/int/bool/str) with bounds,
    choices, default, and owner; definition errors raise
    `ParameterError`.
  - `ConfigStore`: thread-safe registry; `apply()` is all-or-nothing
    and the *single* enforcement point for parameter validity.
  - `Tuner` protocol (`tune(ctx) -> Proposal | None`), `Proposal`
    (changes + baseline/estimate/evidence/seed), `TuningContext`.
  - `Mode` (OFFLINE/SHADOW/CANARY/APPLIED) + `ModeDriver` protocol
    with a driver registry; default recording drivers change nothing.
  - `OptimizationController.run_cycle()`: tuners propose →
    **controller validates every change against the store** (unknown /
    out-of-bounds values raise `ParameterError` before any driver
    sees them) → constraints checked (`ConstraintViolation` rejects)
    → driver disposes → run journaled. A crashing tuner is isolated
    and skipped; the cycle always completes.

## Verification

22 new tests (parameter validation, all-or-nothing apply,
snapshot/restore, offline recording, crash isolation, constraint
rejection, out-of-bounds never reaching the driver, journaling);
`ruff` and `mypy` clean.
