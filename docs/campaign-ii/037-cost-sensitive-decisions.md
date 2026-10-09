# Slice 037 — Cost-sensitive decisions

## What existed before
- `DecisionPolicy.minimum_probability`: the most *probable* outcome wins.
  Nothing priced mistakes — a missed fraud and a false alarm were equal.

## What changed
- **`hugrgate/contracts/cost.py`** (new, kind `"cost-sensitive"`):
  - `CostMatrix`: `cost[predicted][true]` over an outcome list; guards —
    non-empty unique outcomes, square rows/columns, no extras, costs ≥ 0
    (bool rejected). Non-zero diagonals allowed deliberately (correct but
    expensive actions exist).
  - `expected_cost(matrix, distribution, predicted)` = Σ p(true)·cost.
  - `min_cost_decision` — Bayes rule for costs; deterministic tie-break by
    outcome order. Demonstrated: p(legit)=0.8 yet flagging fraud is optimal
    (8.0 < 20.0 expected cost).
  - `CostSensitiveContract(DecisionContract)`: outcomes + matrix,
    `decide(distribution)` → (label, expected cost), `regret(distribution,
    chosen)` ≥ 0 vs optimal.
- **`hugrgate/contracts/__init__.py`**: lazy `cost` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Distributions are re-validated (keys ⊆ outcomes, normalized) at every
  decision call — a stale or foreign distribution must not silently drive
  a priced decision.
- Foundation for 038 (utility) and 039 (risk), which reuse the
  matrix/decision-rule shape.

## Tests
- `tests/test_contracts_037.py`: 20 tests — expected-cost math, the
  max-prob vs min-cost divergence, tie-breaks, regret (0 for optimal),
  matrix guards (negative, non-square, extras, duplicates, bools),
  distribution guards, round-trips.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/cost.py`, `tests/test_contracts_037.py`.
