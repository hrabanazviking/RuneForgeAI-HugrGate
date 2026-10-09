# Slice 386 — Multi-agent dispatch

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_386_dispatch.py` (9 tests)

## What already existed

One ticket went to one agent. Hard problems — and the
disagreement handling (392) and fusion (391) slices — need
fan-out with reconciliation.

## What was built

- `hugrgate/agents/dispatch.py` — `MultiAgentDispatch`:
  `dispatch(ticket, calls, strategy=...)` over `parallel`
  (collect all), `race` (lowest-latency success wins), `quorum`
  (first *k* successes; missed quorum is a failed dispatch).
  Execution is sequential and deterministic by design (replay,
  slice 397, demands repeatable order); per-call exceptions
  become failed results, never propagate; out-of-range
  confidences are failures. Emits `dispatch.completed` on the
  bus with winner/strategy/failure counts.

## Verification

`pytest tests/test_agents_386_dispatch.py` — 9 passed (parallel
collect/partial/all-fail, race fastest + skips failures, quorum
met/missed, bad confidence, validation, bus signal). `ruff
check` clean, `mypy` clean.
