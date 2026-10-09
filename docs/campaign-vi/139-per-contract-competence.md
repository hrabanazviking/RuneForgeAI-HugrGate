# Slice 139 — Per-contract competence

**Status:** complete. **Tests:** `tests/test_adaptive_contract_competence.py` — 9 tests green.

## What existed before

Domains (slice 138) are coarse: "numeric" covers thermostat readings and
derivatives pricing alike, and a backend can be superb at `fraud-score/v3`
while mediocre at `fraud-score/v4`.

## What was built

`hugrgate/adaptive/contract_competence.py` — `PerContractCompetence`:

- One profile per `(backend, contract)`; contract resolution from
  `spec.metadata["contract"]` (+ `"/v" + metadata["version"]` when present),
  falling back to spec type — graceful degradation to slice-138 behavior,
  never an invented contract.
- Same fallback ladder as domains (exact → global → None), same
  `ranked_in_contract`, `contracts()`, serialization
  (`adaptive-contract-competence/v1`).

## Integration

- Mirrors slice 138's architecture on the finer contract key; reads
  `DecisionSpec.metadata`.

## Verification

- `pytest tests/test_adaptive_contract_competence.py` — 9/9 green:
  contract/version resolution, v3-vs-v4 distinction preserved (the case a
  domain average erases), fallback, telemetry batch update, serialization.
- `mypy hugrgate/adaptive` — clean.
