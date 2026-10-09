# Slice 378 — Intent routing

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_378_intent.py` (9 tests)

## What already existed

Contracts (376) declare which intents an agent handles; triage
(377) classifies bus signals. Nothing mapped raw input text to an
owning agent.

## What was built

- `hugrgate/agents/intent.py` — `IntentRouter`: keyword-scored
  `(intent, agent_id)` registrations with static priority.
  Scoring is case-insensitive on word boundaries (`tokenize()`);
  winners maximize `keyword_hits + priority`; ties break by
  `(agent_id, intent)` for run-to-run stability. `intent_hint`
  (from an upstream classifier) restricts candidates. Unmatched
  input goes to the fallback agent (confidence 0, `fallback=True`);
  with no fallback the router raises `AgentNotFound` instead of
  guessing. Registrations re-declaring the same pair replace the
  old one.
- Contract integration: when the router knows an agent's contract,
  registration of an undeclared intent raises
  `AgentContractViolation` — the router can never send traffic to
  an agent that didn't claim the intent.

## Verification

`pytest tests/test_agents_378_intent.py` — 9 passed
(word-boundary anti-false-positive, tie-breaking, hint
restriction, fallback, contract check, validation). `ruff check`
clean, `mypy` clean.
