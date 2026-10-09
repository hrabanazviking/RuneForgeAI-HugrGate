# Slice 394 — Runaway escalation guard

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_394_runaway.py` (5 tests)

## What already existed

The loop-breaker (393) catches cycles, escalation (384) caps
depth per contract — but nothing capped *total* ticket
consumption (steps, tokens, escalations) or offered a global
halt.

## What was built

- `hugrgate/agents/runaway.py` — `RunawayGuard`: per-ticket
  counters for escalations/steps/tokens with configurable
  `RunawayLimits`; `check_escalation()` / `consume()` raise
  terminal `AgentRunaway` past limits (not recoverable — the
  ticket is dead); `trip_kill_switch()` halts all tickets
  (operator panic button) with re-arm; every breach and kill
  publishes `agent.runaway` (critical) with counter values.
- Composition: wire the loop-breaker's `agent.loop` signal into
  `check_escalation` and cycles cost escalation budget too.

## Verification

`pytest tests/test_agents_394_runaway.py` — 5 passed
(escalation/step/token budgets, kill-switch halt + re-arm,
breach bus signal with counters, reset, limit validation).
`ruff check` clean, `mypy` clean.
