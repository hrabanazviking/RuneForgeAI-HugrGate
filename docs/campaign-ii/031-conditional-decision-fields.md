# Slice 031 — Conditional decision fields

## What existed before
- `CompositeContract` (slice 030): every field required, always — no way to
  say "field B only when field A = 'x'".

## What changed
- **`hugrgate/contracts/conditional.py`** (new, kind
  `"conditional-composite"`):
  - `FieldCondition(on_field, op, expected)` — frozen dataclass; ops `eq`,
    `ne`, `in`, `not_in`, `gt`, `ge`, `lt`, `le`; `in`/`not_in` require a
    real collection; `satisfied_by` evaluates with `TypeError` converted to
    `ContractError(condition_type_mismatch)`; dict round-trip.
  - `ConditionalCompositeContract(CompositeContract)`: `conditions:
    Dict[str, FieldCondition]`. Construction guards: condition targets and
    references must be known fields, no self-reference, no cycles (DFS).
  - `active_fields(value)` — fixpoint activation over possibly-partial
    mappings; conditions chain (a field conditional on a conditional field
    cascades).
  - `activation_report(value)` — `{field: is_active}` for explanations.
  - `validate_value`: unconditional fields validated first (conditions read
    them), then only *active* fields required/validated; a value for an
    *inactive* field is rejected (`inactive_field_provided`) — a
    contradiction, not dead data.
- **`hugrgate/contracts/__init__.py`**: lazy `conditional` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- Subclasses `CompositeContract` (kind overridden) — conditionality is a
  strict extension of structure, reusing field validation and
  serialization wholesale.
- Strict on inactive-but-provided: silently carrying a value for a field
  the contract says is off hides bugs; rejection is the honest behavior.

## Tests
- `tests/test_contracts_031.py`: 22 tests — activation/inactivation,
  chained cascades, all comparison ops, `in`/`not_in`, partial mappings,
  activation reports, round-trips, and all construction/validation
  rejections (cycles, self-ref, unknown refs, bad ops, type mismatches).
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/conditional.py`, `tests/test_contracts_031.py`.
