# Slice 389 — Agent cost routing

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_389_cost.py` (7 tests)

## What already existed

`hugrgate.routing.cost` prices *backends*; nothing priced
*agents* or held per-agent wallets.

## What was built

- `hugrgate/agents/cost.py` — `CostRouter`: per-agent price tags
  and budgets in the same abstract units as the contract
  `max_cost` SLO (376). `spend()` records actuals;
  `authorize()` is the routing predicate (unbounded budgets
  always fit; exhausted budgets are a hard stop even for
  zero-cost estimates); `pick_cheapest()` with optional
  per-decision cap (unknown costs sort as +∞; nothing
  affordable → `AgentNotFound`); edge-triggered
  `cost.budget_exhausted` bus signal; top-ups reset exhaustion.
- These are *routing* budgets; hard execution budgets land in
  slice 395.

## Verification

`pytest tests/test_agents_389_cost.py` — 7 passed (ledger math,
hard-stop exhaustion, edge-triggered signal, cheapest pick +
ties + caps, budget top-up/unbounded). `ruff check` clean,
`mypy` clean.
