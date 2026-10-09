# Slice 045 — Contract composition

## What existed before
- Inheritance (044): *is-a* specialization of one base. No *and*: no
  field-set merging, no joint (A×B) decisions, no stacking wrappers.

## What changed
- **`hugrgate/contracts/composition.py`** (new):
  - `merge(*contracts, contract_id, on_conflict="error"|"left"|"right")`:
    union of fields for same-concrete-sub-kind composites; identical
    field definitions merge idempotently; conditions union (conditional),
    constraints concatenate (constrained). Cross-sub-kind merges are
    *rejected* (`heterogeneous_merge`) — silently dropping conditions or
    constraints would lie about the result.
  - `product(a, b, contract_id, name_a, name_b)`: the joint decision —
    any two contracts/specs as two named composite fields.
  - `with_deadline(contract, contract_id, ...)`: stack slice-040 temporal
    bounds onto any contract.
- **`hugrgate/contracts/__init__.py`**: lazy `composition` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- `derive_contract` (044) is single-base override; `merge` is its
  multi-base union sibling — the two compose the full
  specialize/combine story.
- Conflict default is `error`: merging is explicit, and silent
  last-wins would hide contract bugs.

## Tests
- `tests/test_contracts_045.py`: 15 tests — field union, idempotent
  identical fields, all three conflict policies, condition union,
  constraint concatenation, heterogeneous rejection, product, deadline
  stacking, round-trips.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/composition.py`, `tests/test_contracts_045.py`.
