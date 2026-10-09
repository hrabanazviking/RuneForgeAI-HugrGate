# Slice 469 — Rollback triggers

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_469_rollback.py` (10 tests)

## What existed

The canary driver had the rollback *mechanism* (lease snapshots) but
no declarative *policy*: nothing watched metrics and fired
automatically.

## What changed

- `hugrgate/autotune/rollback.py`:
  - `RollbackTrigger`: one watched metric, gt/lt threshold,
    `sustained` consecutive breaches required (a single bad sample
    never fires); an unreadable metric fails closed via
    `RollbackError`;
  - `RollbackController`: `evaluate()` (would-fire, no side
    effects) vs `check()` (evaluate + restore); firing disarms the
    trigger until deliberate `reset()`; every event journaled;
  - a failed restore raises `RollbackError` — a state-integrity
    emergency, never retried blindly;
  - `as_canary_guardrails()`: converts triggers to the driver's
    `(ok, reason)` guardrails with **exactly one restore, owned by
    the driver** (the controller only records the event).

## Verification

10 new tests (sustained firing, counter reset on recovery, lt
direction, duplicate/unknown triggers, bad specs, metric-crash
fail-closed, restore-failure → RollbackError, missing restore,
end-to-end canary guardrail rollback with a single restore);
`ruff` and `mypy` clean.
