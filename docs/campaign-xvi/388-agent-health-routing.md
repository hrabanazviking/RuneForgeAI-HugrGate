# Slice 388 — Agent health routing

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_388_health.py` (7 tests)

## What already existed

The registry (387) tracks a boolean health flag but nothing
*computed* health from outcomes; `ToolRouter` accumulates
reliability stats with no consumer.

## What was built

- `hugrgate/agents/health.py` — `HealthRouter`: per-agent EWMA
  success scores (unknown agents start neutral at 0.5), separate
  EWMA latency tracking (slow-but-correct ≠ failing), `pick()`
  with `min_score` bar and deterministic tie-breaks (nothing
  qualifying → `AgentNotFound`, never a blind route),
  `degraded()` threshold checks, edge-triggered `health.degraded`
  bus signals (fires on crossing, not every bad report), and
  `sync_registry()` pushing flags into the registry so sick
  agents drop out of `healthy_only` lookups.

## Verification

`pytest tests/test_agents_388_health.py` — 7 passed (EWMA math,
latency separation, tie-breaks, min-score failure, edge-triggered
degrade/recover, registry sync). `ruff check` clean, `mypy`
clean.
