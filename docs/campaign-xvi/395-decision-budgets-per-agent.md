# Slice 395 — Decision budgets per agent

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_395_budgets.py` (6 tests)

## What already existed

Three budget-adjacent systems with three jobs: cost router
(389, routing-time wallets), runaway guard (394, per-ticket
ceilings). Nothing budgeted *agents* across tickets.

## What was built

- `hugrgate/agents/budgets.py` — `BudgetLedger`: `allocate()`
  per-agent `DecisionBudget` (decisions/tokens/latency_ms);
  `consume()` charges and raises `AgentBudgetExhausted` naming
  the exhausted dimension with used/limit details (checked in
  decisions → tokens → latency order); exact-limit consumption
  allowed; `reset()` opens a new window; `top_up()` adds
  headroom (supervisor/operator action, never the agent's).

## Verification

`pytest tests/test_agents_395_budgets.py` — 6 passed (each
dimension exhausts, exact-limit boundary, unallocated
rejection, reset/top-up, validation). `ruff check` clean,
`mypy` clean.
