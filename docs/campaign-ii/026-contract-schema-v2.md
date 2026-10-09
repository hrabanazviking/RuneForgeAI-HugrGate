# Slice 026 — Contract schema v2

## What existed before
- `hugrgate/spec.py`: `DecisionSpec` — unversioned dataclass, 5 fixed types
  (`categorical`, `binary`, `ordinal`, `numeric`, `multilabel`), no
  identity, no versioning, no canonical serialization, no kind registry.
- `hugrgate/errors.py`: no contract-specific error type.

## What changed
- **`hugrgate/errors.py`**: added `ContractError(SpecError)` (`code="contract_error"`).
  Additive only — existing `except SpecError` handlers keep working; the
  top-level `hugrgate.__all__` snapshot is untouched.
- **`hugrgate/contracts/schema.py`** (new): the v2 schema foundation.
  - `SCHEMA_VERSION = "2.0"`, `SUPPORTED_SCHEMA_VERSIONS = ("2.0",)`.
  - `DecisionContract` dataclass: `contract_id` (required, non-empty),
    `name`, `description`, JSON-serializable `metadata`; `kind` ClassVar.
  - `to_dict()` / `from_dict()` with schema-version gating (unknown or
    unsupported versions raise `ContractError` with a migration hint);
    kind dispatch through the `CONTRACT_KINDS` registry populated by the
    `@register_kind` decorator (duplicate/empty kinds rejected).
  - `canonical_hash()`: sha256 over canonical JSON — stable content identity
    for caching/provenance/negotiation.
  - `validate_value()` hook (base: JSON-serializability) and non-raising
    `check_value()`; `describe()` one-line summary.
- **`hugrgate/contracts/__init__.py`** (new): package surface re-exporting
  the schema API with an explicit `__all__`.
- **`tools/gen_arch_map.py`**: new `"contract-engine"` layer listing
  `hugrgate.contracts` and `hugrgate.contracts.schema`.
- Regenerated machine docs: `docs/campaign-i/architecture-map.md`,
  `docs/campaign-i/003-public-api-inventory.md`,
  `docs/campaign-i/manifest.json` + `001-repository-truth-audit.md`.

## Design decisions
- `DecisionSpec` left byte-identical — v2 lives alongside v1; migration is
  slice 047's job (forward reference already in the version error message).
- Per-instance machine codes follow the slice-10 taxonomy convention:
  class-level `.code` stays fixed, instance codes live in
  `details["code"]` (e.g. `unknown_contract_kind`).
- Base `validate_value` accepts any JSON value; concrete kinds narrow it —
  every later Campaign II slice extends this hook.

## Tests
- `tests/test_contracts_026.py`: 19 tests — round-trip, hash stability and
  sensitivity, version gating (incl. migration hint), kind registry
  (duplicate/empty/unknown), non-serializable metadata/value rejection,
  `ContractError`/`SpecError` subtyping.
- Full suite: **384 passed** (baseline 365 + 19 new); mypy clean
  (44 source files).

## Evidence
- `git show --stat HEAD` on branch `gjallarbu/campaign-ii`:
  `hugrgate/errors.py`, `hugrgate/contracts/__init__.py`,
  `hugrgate/contracts/schema.py`, `tests/test_contracts_026.py`,
  `tools/gen_arch_map.py`, regenerated campaign-i docs.
