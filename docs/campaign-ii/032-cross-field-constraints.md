# Slice 032 — Cross-field constraints

## What existed before
- `ConditionalCompositeContract` (031): governs field *activation*; no way
  to state *invariants* spanning fields (`start < end`, `a + b ≤ 100`).

## What changed
- **`hugrgate/contracts/crossfield.py`** (new, kind
  `"constrained-composite"`):
  - `FieldConstraint(fields, op, target, description)` — frozen, declarative,
    serializable. Ops: `lt/le/eq/ne/gt/ge` (one field vs literal or
    `{"field": name}`), `sum_lt/sum_le/sum_eq/sum_ge/sum_gt` (numeric sum vs
    target), `all_distinct` (≥2 fields pairwise distinct). Arity and target
    shapes validated at construction.
  - `check(value) -> Optional[str]`: never raises on bad data — missing
    fields, incomparable types, and non-numeric sums become violation
    messages, enabling aggregation.
  - `ConstrainedCompositeContract(CompositeContract)`: `constraints` list;
    construction rejects constraints on unknown fields; `violations(value)`
    collects every violation; `validate_value` runs per-field validation
    first, then raises one `ContractError` (`cross_field_violation`) with
    all violations in `details["violations"]`.
  - `describe()` renders invariants readably (`start < field 'end'`).
- **`hugrgate/contracts/__init__.py`**: lazy `crossfield` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Constraints are *data, not callables* — serializable, describable,
  auditable (law 14). One bug found by tests: the violation message used
  the resolved target where the raw field-ref was needed — fixed.
- Aggregation over fail-fast: a decision violating three invariants
  should report all three.

## Tests
- `tests/test_contracts_032.py`: 23 tests — field-ref targets, all sum
  ops, distinctness, boundary values (`le`/`ge` inclusive), violation
  aggregation (3 violations → 3 messages), type-mismatch-as-violation,
  construction guards (unknown fields/targets, bad ops/arity/targets),
  round-trips.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/crossfield.py`, `tests/test_contracts_032.py`.
