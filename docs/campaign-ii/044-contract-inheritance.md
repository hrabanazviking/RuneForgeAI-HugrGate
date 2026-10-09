# Slice 044 — Contract inheritance

## What existed before
- Contracts were standalone: no derivation, no specialization, no way to
  check that a specialized contract is a safe substitute for its base.

## What changed
- **`hugrgate/contracts/inheritance.py`** (new):
  - `derive_contract(base, contract_id, *, name, description, metadata,
    **overrides)`: same-kind child via dataclass-field introspection
    (private/recomputed fields skipped); unknown override names rejected
    up front; metadata deep-merges with child winning; the base's
    canonical hash is recorded as `derived_from` (provenance).
  - `is_compatible(child, base)`: Liskov over the *value space* — every
    value the child accepts, the base accepts. Per-kind handlers:
    ordinal (subsequence, order-preserving), numeric-interval (range
    narrowing + stricter guards), multilabel (label/rule inclusion),
    distribution/cost/utility/risk (outcome inclusion), nested
    (leaf-path inclusion), hierarchical (label inclusion), composite
    (identical field sets, recursive per-field), conditional (equal
    conditions), constrained (base constraints ⊆ child's),
    timed (inner compatible + stricter bounds), context/features
    (required/type/extra discipline via a type lattice),
    explanation (demands ≥ base's). Kind mismatch → False; unhandled
    kinds → conservative payload equality.
- **`hugrgate/contracts/__init__.py`**: lazy `inheritance` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Compatibility is about *values*, not parameters: a cost child with
  different prices but identical outcomes is compatible.
- Derivation guards fire before compatibility is even asked (dropping a
  required label fails at derive time — tests confirmed).
- Handlers are defensive: unexpected shapes return False rather than
  raising.

## Tests
- `tests/test_contracts_044.py`: 19 tests — derivation (overrides,
  provenance chain, metadata merge, unknown/invalid overrides),
  compatibility across 7 kinds (both directions), kind mismatch,
  transitivity, hash stability.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/inheritance.py`, `tests/test_contracts_044.py`.
