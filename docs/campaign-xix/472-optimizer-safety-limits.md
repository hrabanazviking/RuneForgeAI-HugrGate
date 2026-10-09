# Slice 472 — Optimizer safety limits

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_472_limits.py` (10 tests)

## What existed

Nothing bounded the optimizer: a tuner could propose any change, in
any mode, at any rate, with no kill switch and no frozen params.

## What changed

- `hugrgate/autotune/limits.py`:
  - `SafetyLimits`: kill switch, frozen params, blast radius
    (max params per proposal), step size (max fraction of bound
    width per proposal, measured from the *current* value), mode
    allowlist, cycle rate limit — bad policies rejected at
    construction with `UnsafeProposalError`;
  - `SafetyEnforcer`: `check_proposal` / `check_rate`;
    `as_driver()` wraps any `ModeDriver` so the check runs after
    controller validation and before disposal (rejections surface
    as REJECTED dispositions, not crashes); `guarded_controller()`
    wires the wrapping in place. The controller itself is
    untouched — safety is a driver decorator.

## Verification

10 new tests (kill switch, frozen params, blast radius, step size
from current value, mode allowlist, sliding-window rate limit, bad
policy rejection, guarded-driver reject/pass, controller wiring);
`ruff` and `mypy` clean.
