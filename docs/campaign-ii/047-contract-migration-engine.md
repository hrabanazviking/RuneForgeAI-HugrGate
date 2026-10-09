# Slice 047 — Contract migration engine

## What existed before
- v1 `DecisionSpec` and v2 `DecisionContract` lived side by side with no
  bridge; `contract_from_dict`'s version error promised a
  `hugrgate.contracts.migration` module that did not exist.

## What changed
- **`hugrgate/contracts/migration.py`** (new):
  - `spec_to_contract(spec, contract_id, ...) -> (contract, MigrationReport)`:
    categorical → flat nested-categorical; binary → nested-categorical
    `["true","false"]` with the statement preserved in `description`
    (warning); ordinal → ordinal with default anchors; numeric →
    numeric-interval; multilabel → multilabel-cardinality with no rules.
    Metadata carries over. Verified: every v1-accepted value validates
    under the migrated contract.
  - `contract_to_spec(contract)`: reverse for the four unambiguous kinds
    (flat nested → categorical; `["true","false"]`+description → binary;
    ordinal; numeric-interval; rule-free multilabel). Guarded numeric /
    ruled multilabel / exotic kinds raise `ContractError` instead of
    silently degrading.
  - `MigrationReport(source_version, target_version, result, warnings,
    lossy)` with a one-line `describe()`.
  - `MIGRATIONS` registry `(from, to) → fn` with `register_migration`
    (rejects duplicates/empties); `migrate(d, to_version="2.0")`
    dispatches on `schema_version` (absent = `"1.0"`), passes v2 dicts
    straight through, raises on unknown paths. `("1.0","2.0")`
    registered — the `from_dict` error's promise is now real.

## Design decisions
- Migrations are total on their documented domain and loud elsewhere;
  the reverse path prefers raising over silent loss (binary statement
  only survives because the forward path preserved it).
- A v1 dict with an unknown spec type raises `SpecError` (the parent of
  `ContractError`), so `migrate_spec_dict` catches `SpecError` — caught
  by a test with `{"type": "bogus"}`.

## Tests
- `tests/test_contracts_047.py`: 19 tests — forward migration of all
  five v1 types, value-space agreement, binary round-trip, reverse
  rejections, registry dispatch, guard clauses.
- Full suite + mypy green at commit.

## Evidence
- `hugrgate/contracts/migration.py`, `tests/test_contracts_047.py`.
