# Slice 038 — Utility matrices

## What existed before
- `CostMatrix` (037): losses ≥ 0, minimized. No gains, no maximization, no
  cost↔utility bridge.

## What changed
- **`hugrgate/contracts/utility.py`** (new, kind `"utility"`):
  - `UtilityMatrix`: `utility[decision][outcome]`, finite reals (negatives
    allowed; NaN/inf/bool rejected), square over outcomes.
  - `expected_utility`, `max_utility_decision` (ties → outcome order).
  - `UtilityContract(DecisionContract)`: `decide` → (label, EU),
    `regret` = optimal EU − EU(chosen) ≥ 0.
  - `as_cost_matrix()`: the duality bridge — `C = max(U) − U` is a valid
    (non-negative) cost matrix. Tested: max-EU under U and min-cost under
    C agree on multiple distributions, not just claimed.
- **`hugrgate/contracts/__init__.py`**: lazy `utility` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Utility reuses the cost module's shape deliberately (matrix + decision
  rule + contract + regret) so the two are interchangeable faces of one
  decision theory; `utility.py` → `cost.py` is a one-way edge (no cycle).

## Tests
- `tests/test_contracts_038.py`: 18 tests — EU math, max-EU decisions,
  the duality property across 4 distributions, non-negative dual costs,
  regret, finiteness/square guards, round-trips, tie boundaries.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/utility.py`, `tests/test_contracts_038.py`.
