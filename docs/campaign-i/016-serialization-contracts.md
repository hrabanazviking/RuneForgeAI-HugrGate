# Slice 016 — Serialization contracts

**Date:** 2026-10-09 · **Tests:** `tests/test_serialization_contracts.py` (14 tests)

## Audit of what existed

Round-trip pairs existed for: `DecisionSpec`, `DecisionResult`
(`result_from_dict`), `DecisionPolicy` (`policy_to_dict` /
`policy_from_dict` in `client.py`), `DaemonConfig`, `HugrGateError`,
`Abstention`, `ModelManifest`, `Rule`/`RuleBackend`, `LadderRung`
(`to_dict` only), `LadderAuditEntry` (`to_dict` only), `DriftReport`
(`to_dict` only). Missing entirely: `DecisionRecord`,
`ThresholdConfig`, `NumericBand`, `LadderRung.from_dict`,
`DecisionPolicy.to_dict`.

## Changes

- `DecisionRecord.to_dict` / `from_dict` (provenance): full field
  coverage incl. `prev_hash`/`record_hash`; `from_dict` raises
  `SpecError` on missing required keys. Chain hashes survive the
  round-trip (verified by test).
- `NumericBand.to_dict` / `from_dict`, `ThresholdConfig.to_dict` /
  `from_dict` (threshold): strict unknown-key rejection on
  `ThresholdConfig.from_dict` (`PolicyError`), matching the
  `policy_from_dict` precedent.
- `LadderRung.from_dict` (ladder): strict unknown-key rejection
  (`SpecError`); value validation via the existing `__post_init__`.
- `DecisionPolicy.to_dict()` (policy): new canonical method;
  `client.policy_to_dict` now delegates to it (single source of
  truth).

## Contract pinned by tests

`from_dict(to_dict(x)) == x` for spec / result / policy / record /
threshold-config / ladder-rung, plus `json.dumps(to_dict(x))`
JSON-safety, unknown-key rejection, and missing-key/valdiation
failures. One-way `to_dict`s (audit entries, drift reports) left as
is: they are telemetry, not rehydrated state.

## Verification

14 new tests green; full suite 471 passed; mypy clean on 43 files.
