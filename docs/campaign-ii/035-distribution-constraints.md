# Slice 035 — Distribution constraints

## What existed before
- `validate_result` / ordinal `validate_distribution`: well-formedness only
  (keys ⊆ space, values ∈ [0,1], sum ≈ 1). A backend emitting `{"a": 1.0}`
  forever passes — well-formed and useless.

## What changed
- **`hugrgate/contracts/distributions.py`** (new, kind `"distribution"`):
  - `DistributionConstraint(op, threshold, labels, description)` — frozen,
    declarative, serializable. Ops: `min_top1`/`max_top1` (decisiveness
    floor / overconfidence cap), `min_margin` (top1−top2 gap),
    `min_entropy`/`max_entropy` (Shannon, nats), `max_support` (outcomes
    above ε), `min_mass` (label-set mass floor). Threshold shapes validated
    per op at construction.
  - `check(distribution)`: never raises — malformed distributions become
    violation messages, enabling aggregation.
  - `DistributionContract(DecisionContract)`: `outcomes` + `constraints`;
    `validate_value` checks outcome membership; `validate_distribution`
    aggregates well-formedness (keys ⊆ outcomes) and every constraint
    violation into one `ContractError`; `check_distribution` non-raising.
  - `shannon_entropy` helper (zero-mass entries contribute 0).
- **`hugrgate/contracts/__init__.py`**: lazy `distributions` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- `min_margin` on a single-outcome distribution compares against an
  implicit 0.0 runner-up — a lone certain outcome is maximally decisive.
- Construction uses `field(default_factory=list)` with non-empty checks in
  `__post_init__` (an earlier `None`-default draft was replaced for
  mypy-cleanliness).

## Tests
- `tests/test_contracts_035.py`: 23 tests — entropy math (uniform→ln 4),
  every op success/failure, aggregation, malformed-as-violation,
  threshold/label guards, round-trips, single-outcome and threshold-edge
  boundaries.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/distributions.py`, `tests/test_contracts_035.py`.
