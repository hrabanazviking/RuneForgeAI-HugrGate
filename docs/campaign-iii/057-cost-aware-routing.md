# Slice 057 — Cost-aware routing

## What existed
`DecisionPolicy.max_cost` existed as a field but nothing in routing
enforced it: rung selection ignored cost beyond the synthesizer's blend
weights, and no spend was ever tracked.

## What changed
- **`hugrgate/routing/cost.py`** (new):
  - `budget_for(ctx)`: effective budget — `options.max_cost` overrides
    `policy.max_cost`.
  - `CostLedger`: per-request accounting with `reserve()` (plan time,
    cumulative — a ladder of individually-cheap rungs cannot silently
    exceed the budget), `spend()` (run time), `remaining`, and a
    `to_dict()` audit view. Unbounded (`None`) ledgers afford everything.
  - `CostAwarePlanner`: top-down reservation walk; unaffordable rungs
    pruned with reasons; survivors carry `params["cost_estimate"]`; the
    ledger rides on the plan for inspection.
- **`hugrgate/routing/architecture.py`**: `LadderRouterV2` accepts
  `cost_ledger=`; `note_cost(backend, result)` records actuals from
  `result.metadata["cost"]` when backends report it, else the estimate;
  `SerialPlanExecutor` calls it after every attempted rung (spend
  happens whether the gate clears or not).

## Integration
Reuses the existing `policy.max_cost` field (no policy change needed);
validation, provenance, privacy, abstention semantics unchanged.

## Tests
`tests/test_routing_057.py` (9 tests): ledger reserve/spend/remaining
math, negative-input rejection, unbounded ledger, options-over-policy
precedence, unaffordable-rung pruning, cumulative reservation pruning,
empty cost plan → `Abstention`, actual-vs-estimate spend recording,
no-ledger safety.

## Evidence
- `pytest tests/test_routing_057.py` → 9 passed.
