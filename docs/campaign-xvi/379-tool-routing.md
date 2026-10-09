# Slice 379 — Tool routing

**Date:** 2026-10-09 · **Tests:** `tests/test_agents_379_tools.py` (8 tests)

## What already existed

Contracts declare which tools an agent may use (376), but nothing
stood between an agent and a tool call — a compromised or buggy
agent could invoke anything.

## What was built

- `hugrgate/agents/tools.py` — `ToolRouter`, the choke point for
  tool invocation. `ToolPolicy` per agent: allowed/denied tools
  (**deny wins**), per-ticket call budgets, per-tool argument
  schemas. `authorize()` checks policy → allow/deny → contract
  tool list → argument schema → call budget, minting a `call_id`
  grant; `record_result()` closes grants and accumulates per-tool
  reliability stats (failure rate, mean latency) for the health
  router (slice 388).
- Failure semantics: missing policy / denied tool / bad args →
  `AgentContractViolation` (details carry the schema violations);
  exhausted per-ticket budget → `AgentBudgetExhausted`.

## Verification

`pytest tests/test_agents_379_tools.py` — 8 passed (deny-wins,
contract cross-check, arg schema, per-ticket budget isolation,
stats). `ruff check` clean, `mypy` clean (fixed a tuple-key dict
annotation mypy flagged).
