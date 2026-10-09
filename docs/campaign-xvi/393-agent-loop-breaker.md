# Slice 393 — Agent loop-breaker

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_393_loopbreak.py` (7 tests)

## What already existed

Nothing detected delegation cycles — a planner↔worker ping-pong
would burn budget until some outer timeout noticed.

## What was built

- `hugrgate/agents/loopbreak.py` — `LoopBreaker`: call-stack
  discipline for delegation. `observe()` pushes onto the
  ticket's stack (caller must be the stack top — chains, not
  graphs); pushing an agent already on the stack raises
  `AgentLoopDetected` with the cycle path; stacks deeper than
  `max_depth` trip too. `return_to()` pops on delegation
  completion so legitimate returns never trip the breaker.
  Detection emits `agent.loop` (critical) on the bus — triage's
  urgent rules already route it hot. Purely observational: it
  detects, the runaway guard (394) and escalation (384) decide.

## Verification

`pytest tests/test_agents_393_loopbreak.py` — 7 passed (chain +
return, cycle path in details, self-loop, ping-pong, depth cap,
chain discipline, ticket isolation, bus signal). `ruff check`
clean, `mypy` clean.
