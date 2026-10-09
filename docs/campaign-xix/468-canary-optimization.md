# Slice 468 — Canary optimization

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_468_canary.py` (10 tests)

## What existed

Proposals went from shadow comparison straight to fleet-wide
application with no fractional rollout and no automatic way back.

## What changed

- `hugrgate/autotune/modes.py`: `CanaryDriver` for `Mode.CANARY` —
  applies the proposal through the store (type/bounds validation
  still holds) but wraps it in a `CanaryLease` carrying the
  pre-canary snapshot, traffic fraction, and expiry:
  - `poll()` heartbeat: guardrail breach → restore snapshot
    (`rolled_back`); lease expiry → restore (`expired`); healthy →
    `hold`;
  - guardrails fail closed (a raising guardrail counts as a breach);
  - `promote()` keeps the config; only one canary active at a time
    (a second proposal is REJECTED, not queued);
  - injectable clock for deterministic tests.
  - Slice 469 builds declarative rollback triggers on this
    mechanism.

## Verification

10 new tests (apply+lease, single-active rejection, hold, breach
rollback, crash-fail-closed, expiry, promote, bad fraction,
controller canary cycle); `ruff` and `mypy` clean.
