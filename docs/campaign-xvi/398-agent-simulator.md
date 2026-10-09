# Slice 398 — Agent simulator

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_398_simulator.py` (7 tests)

## What already existed

Chaos experiments (campaign: `hugrgate.chaos`) fault *models*;
nothing rehearsed *agent* failure modes against the
nervous-system machinery.

## What was built

- `hugrgate/agents/simulator.py` — `AgentSimulator`:
  scripted agents (`honest` / `slow` / `faulty` / `looping` /
  `escalating` / custom callables) played through the real
  `EventBus`, `LoopBreaker`, `RunawayGuard`, and
  `MultiAgentDispatch` via `{"ticket","from","to","intent"}`
  scripts. Per-step `faults` hooks are the chaos injection
  point (e.g. trip the kill switch at step N). `SimulationReport`
  counts successes/failures/loops/runaways/escalations with
  per-agent outcomes; seeded RNG makes runs reproducible.

## Verification

`pytest tests/test_agents_398_simulator.py` — 7 passed
(honest/faulty mix, looping → breaker, escalating → runaway
guard, kill-switch fault hook, custom behaviors, seed
determinism). `ruff check` clean, `mypy` clean.
