# Slice 033 — Rich ordinal semantics

## What existed before
- `DecisionSpec(type="ordinal")`: pure order — `low < medium < high` with no
  distances, no scale positions, no interpolation, no distribution checks.

## What changed
- **`hugrgate/contracts/ordinal.py`** (new, kind `"ordinal"`):
  - `OrdinalContract(DecisionContract)`: `levels` + optional `anchors`
    (numeric position per level; default 0..n−1; must be strictly
    increasing in level order — all-or-none, numeric, known levels).
  - Order API: `rank_of`, `anchor_of`, `is_ordered`, `distance`
    (absolute anchor gap), `levels_between` (order-independent).
  - Numeric bridge: `interpolate(x)` → nearest level (ties → lower rank,
    documented); `expected_anchor(distribution)` → expected scale position.
  - `validate_value` (level membership) and `validate_distribution`
    (keys ⊆ levels, values ∈ [0,1], sum ≈ 1).
  - Full serialization round-trip; `describe()` renders the scale.
- **`hugrgate/contracts/__init__.py`**: lazy `ordinal` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Anchors are all-or-none: a partially anchored scale is ambiguous, so it
  is rejected rather than guessed.
- Interpolation ties resolve downward (conservative) and the rule is
  documented on the method — deterministic, no hidden randomness.

## Tests
- `tests/test_contracts_033.py`: 26 tests — default/custom anchors, order
  queries, distances, interpolation (incl. ties, out-of-range clamping),
  expected anchors, distribution validation, round-trips, and every
  anchor/distribution rejection mode.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/ordinal.py`, `tests/test_contracts_033.py`.
