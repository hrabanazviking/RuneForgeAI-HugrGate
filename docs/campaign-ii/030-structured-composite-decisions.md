# Slice 030 — Structured composite decisions

## What existed before
- Every `DecisionSpec` / v2 contract was a *single* decision of one type —
  no way to express one structured judgment with several typed fields.

## What changed
- **`hugrgate/contracts/composite.py`** (new, kind `"composite"`):
  - `CompositeContract(DecisionContract)`: `fields: Dict[str, FieldContract]`
    where `FieldContract = Union[DecisionContract, DecisionSpec]` — fields
    may be v2 contracts *or* v1 specs, bridging both generations before the
    slice-047 migration exists.
  - Strict structural validation: value must be a mapping with *exactly*
    the declared fields — missing and unknown fields both rejected
    (`missing_fields` / `unknown_fields`), so typos never pass silently.
  - Per-field delegation: v2 fields via `validate_value`, v1 fields via a
    `_validate_spec_value` helper (space membership, numeric range, bool
    rejected as numeric); violations re-raised with the field name in
    `details["field"]` and chained cause.
  - Serialization: v2 fields inline, v1 fields under `"decision_spec"`
    (bare `{"type": ...}` dicts also accepted on read); composites nest
    inside composites; `field_names()`, `field_contract()`, `describe()`.
- **`hugrgate/contracts/__init__.py`**: lazy `composite` submodule.
- **`tools/gen_arch_map.py`** + regenerated machine docs.

## Design decisions
- All declared fields required, no extras — conditional/optional fields
  are slice 031's domain; 030 owns strict structure.
- v1 specs embedded directly (not converted) so existing `DecisionSpec`
  semantics are reused verbatim, not duplicated.

## Tests
- `tests/test_contracts_030.py`: 20 tests — mixed v1/v2 fields, nested
  composites, round-trips, bare-spec leniency, all rejection modes
  (missing/unknown fields, bad scalar/numeric/nested values, non-mapping,
  empty fields, bad payloads), bool-is-not-numeric boundary.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/composite.py`, `tests/test_contracts_030.py`.
