# Slice 400 — Agent Nervous System release gate

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_400_release.py` (6 tests)

## What already existed

Twenty-four slices of nervous system with no single verdict on
whether the assembly ships.

## What was built

- `hugrgate/agents/release_gate.py` — `NervousSystem`
  dataclass bundling all 20 campaign components;
  `assemble()` wires a shared bus through triage, escalation,
  review, dispatch, health, cost, notify, loop-breaker, and
  runaway guard; `NervousSystemReleaseGate.run()` executes
  eight checks — contracts-valid, registry-nonempty, bus-alive,
  triage-functional, budgets-allocated, kill-switch-clear,
  provenance-acyclic, replay-deterministic — and returns a
  `ReleaseReport` (passed/failed/summary/to_dict, wire-safe).
  Checks never raise: failures are data.
- `BudgetLedger.allocated()` — public predicate added (slice
  395 module) so the gate can distinguish "no budget" from
  "exhausted budget" without consuming.

## Verification

`pytest tests/test_agents_400_release.py` — 6 passed (healthy
system passes all 8, empty registry fails, missing budgets
fail, tripped kill switch fails, shared-bus assembly). `ruff
check` clean, `mypy` clean.
