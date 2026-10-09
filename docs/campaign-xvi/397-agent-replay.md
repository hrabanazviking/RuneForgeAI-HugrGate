# Slice 397 — Agent replay

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_397_replay.py` (6 tests)

## What already existed

`hugrgate.memory.replay` replays *memory* episodes;
`hugrgate.observability.replay` replays *traces*. Nothing
replayed an *agent's* step inputs/outputs for regression or
determinism checks.

## What was built

- `hugrgate/agents/replay.py` — `AgentReplay`: `record_step()`
  / `record()` capture JSON-safe `(kind, input, output)`
  triples per ticket; `replay(ticket_id, agent_fn, seed=...)`
  re-runs recorded inputs and diffs outputs (`ReplayReport`
  with fidelity fraction, mismatch indexes, notes);
  `check_determinism()` runs the ticket twice and compares.
  Raising functions count as mismatches, never propagate.

## Verification

`pytest tests/test_agents_397_replay.py` — 6 passed (fidelity,
mismatch diffs, raising fn, nondeterminism detection,
JSON-safety, unknown ticket). `ruff check` clean, `mypy`
clean.
