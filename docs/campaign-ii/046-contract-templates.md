# Slice 046 — Contract templates

## What existed before
- Contracts were hand-built per deployment: copied shapes, hand-filled
  amounts, no reuse, no parameter validation.

## What changed
- **`hugrgate/contracts/templates.py`** (new):
  - `TemplateParameter(type, required, default, allowed, description)` —
    frozen; types mirror the context/feature dtype discipline; defaults
    and allowed values validated against the declared type at
    construction.
  - `ContractTemplate(template_id, body, parameters, description)`:
    `${param}` placeholders; a bare `${name}` string injects the raw
    value (numbers/lists/dicts survive), embedded `${name}` interpolates
    textually. Construction rejects undeclared placeholders *and*
    placeholders on optional-without-default params (dangling — could
    never be filled). `instantiate(**params)` validates types/allowed/
    required, substitutes recursively, and runs the result through
    `contract_from_dict` — the product is a fully validated v2 contract.
  - `TemplateLibrary`: named registry with duplicate rejection and
    one-call `instantiate(template_id, **params)`; dict round-trips.
- **`hugrgate/contracts/__init__.py`**: submodules now imported eagerly
  (``import`` form — no self-edge, graph stays acyclic), so **all 17
  contract kinds register the moment the package is imported**.
  `contract_from_dict` no longer fails on kinds whose modules were never
  directly imported (a real footgun the template tests exposed; the
  earlier PEP-562 lazy `__getattr__` was removed as redundant).

## Design decisions
- Strict both ways: template construction catches its own bugs
  (undeclared/dangling placeholders); instantiation catches caller bugs
  (unknown params, bad types, disallowed values, missing required).

## Tests
- `tests/test_contracts_046.py`: 19 tests — raw vs textual substitution,
  defaults, allowed values, library semantics, template round-trips, and
  every strictness rejection.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/templates.py`, `tests/test_contracts_046.py`,
  `hugrgate/contracts/__init__.py`.
