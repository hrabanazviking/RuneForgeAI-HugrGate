# Slice 377 — Event triage API

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_377_triage.py` (9 tests)

## What already existed

Slice 376 delivered the bus; every signal reached every matching
handler with no classification. The nervous system needed a first
processing stage that decides *what deserves a reaction*.

## What was built

- `hugrgate/agents/triage.py` — `EventTriage`: ordered
  first-match-wins rules mapping signals to `route` / `drop` /
  `defer` dispositions over named queues (`default`, `urgent`,
  `defer`, `noise`). Rules carry priority boosts clamped to the
  priority ladder, per-queue and per-rule stats, and optional bus
  publication of `triage.decision` signals with trace continuity.
- `EventTriage.with_defaults()` — standard ruleset: heartbeat /
  telemetry noise dropped, `agent.escalated` / `agent.loop` /
  `agent.runaway` routed urgent with +1 priority, `bulk.*` deferred.
- **Hardening found during testing:** `bus.matches()` only knew
  exact/prefix/wildcard patterns, so the `*.heartbeat` noise rule
  never matched. Extended `matches()` with suffix patterns
  (`*.suffix`) — exact/prefix/suffix/wildcard now covered by tests.

## Integration

- Consumes `AgentSignal` / publishes on `EventBus`; trace ids flow
  through triage decisions so observability spans stay connected.
- The `defer` queue is the input contract for the attention
  prioritizer (slice 383); `urgent` feeds escalation (384).

## Verification

`pytest tests/test_agents_377_triage.py tests/test_agents_376_contract.py`
— 29 passed. `ruff check` clean, `mypy` clean.
