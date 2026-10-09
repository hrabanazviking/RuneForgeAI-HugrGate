# Slice 466 — Offline optimization mode

**Date:** 2026-10-09 · **Tests:** `tests/test_autotune_466_offline.py` (6 tests)

## What existed

The controller's OFFLINE mode used a default recording driver with no
journal API and no way to score a proposal against recorded data after
the fact.

## What changed

- `hugrgate/autotune/modes.py` (new): `OfflineDriver`, a real
  `ModeDriver` for `Mode.OFFLINE`:
  - `handle()` journals the proposal (disposition RECORDED) and
    applies nothing — the live config is provably untouched;
  - `replay(proposal_id, evaluator)` scores the journaled changes
    with an evaluator over recorded telemetry, attaching the
    measured result to the journal entry (evaluator crashes become
    `AutotuneError`, never recorded as successes);
  - `export()` / `clear()` for audit and lifecycle.

## Verification

6 new tests (record-without-apply, replay scoring, unknown proposal,
evaluator-crash isolation, deep-copy export, controller integration
with post-cycle replay); `ruff` and `mypy` clean.
