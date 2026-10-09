# Slice 383 — Attention prioritization

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_383_attention.py` (8 tests)

## What already existed

Triage (377) defers non-urgent signals, but nothing decided what
the agent attends to next — deferred work had no ordering.

## What was built

- `hugrgate/agents/attention.py` — `AttentionPrioritizer`: a
  bounded scored heap queue. Score = weighted priority rank +
  urgency + novelty − cost (weights in `AttentionConfig`). Bounded
  by `max_items`: on overflow the lowest-scored item is shed and
  counted (or the newcomer itself, reported as `"shed-self"`).
  Deterministic order: score → enqueue time → sequence. Frozen
  `AttentionItem`s; `reprioritize()` swaps urgency/novelty/priority
  by id. `peek()`/`pop()`/`__len__`/`stats()`.

## Verification

`pytest tests/test_agents_383_attention.py` — 8 passed (score
ordering, cost penalty, novelty reward, FIFO tie-break, overflow
shed-lowest / shed-self, reprioritize movement, validation).
`ruff check` clean, `mypy` clean.
