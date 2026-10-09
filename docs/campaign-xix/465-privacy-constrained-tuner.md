# Slice 465 — Privacy-constrained tuner

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_465_privacy.py` (8 tests)

## What existed

Nothing in the optimizer understood privacy: a tuner could happily
propose shipping raw sensitive telemetry for a utility win.

## What changed

- `hugrgate/autotune/tuners/privacy.py`:
  `PrivacyConstrainedTuner` maximizes measured utility behind two
  hard privacy fences, integrated with `hugrgate.privacy` (not
  re-implemented):
  - **classification ceiling**: each choice declares its privacy
    class; eligibility is checked with `class_rank()` against the
    deployment's `max_privacy_class` from `ctx.data`, so the
    ladder's ordering stays load-bearing in one place;
  - **epsilon budget**: DP spend per choice (+inf = unbounded, never
    fits a finite budget);
  - `budget` mode (max utility under fences), `minimize` mode (min
    epsilon subject to mean − 1.96·SE >= utility_floor);
  - infeasible incumbents score −inf; evidence is the privacy audit
    trail (class + epsilon + measured utility per choice).

## Verification

8 new tests (epsilon fence, classification ceiling, infeasible
incumbent escape, minimize mode, silence when optimal/empty, bad
ceiling, spec validation, end-to-end offline with ctx.data
plumbing); `ruff` and `mypy` clean.
