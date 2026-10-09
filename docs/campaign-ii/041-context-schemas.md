# Slice 041 — Context schemas

## What existed before
- `HugrGate.decide(..., context)`: the context mapping was opaque — no
  validation, no declared shape. A backend expecting
  `context["locale"]` to be a string received whatever the caller passed.

## What changed
- **`hugrgate/contracts/context.py`** (new, kind `"context-schema"`):
  - `ContextField(name, type, required)` — frozen; types `string`,
    `number`, `integer` (bool excluded), `boolean`, `array`, `object`,
    `any`; per-type `check` with a deliberate type matrix (e.g. `True`
    is not a number/integer, tuples count as arrays).
  - `ContextSchema(fields, allow_extra=True)` — ordered fields, duplicate
    names rejected; `violations(context)` aggregates missing-required,
    mistyped, and (when disallowed) undeclared keys; `validate` raises one
    error; dict round-trip; equality.
  - `ContextContract(DecisionContract)` — the schema as a v2 contract
    (the "decision value" is the context mapping itself), so context
    requirements travel, negotiate, and compose like any contract.
- **`hugrgate/contracts/__init__.py`**: lazy `context` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- `hugrgate/validation.py` deliberately untouched: the slice-004 layering
  rules forbid the contracts layer from importing the contract-engine
  layer. Runtime wiring of context schemas into `decide()` is scheduled
  for slice 050's integration pass.

## Tests
- `tests/test_contracts_041.py`: 19 tests — full type matrix (14 cases),
  required/optional/extra handling, aggregation, non-mapping rejection,
  construction guards, round-trips, equality.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/context.py`, `tests/test_contracts_041.py`.
