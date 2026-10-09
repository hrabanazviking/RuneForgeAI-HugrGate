# Slice 273 — Long soak

**Date:** 2026-10-09 · **Tests:** `tests/test_chaos_soak.py` (6 tests, slow-marked, green)

## What existed before

Every chaos slice tested instants: inject a fault, assert the
response. Nothing asked whether the system *stays* healthy over
time under sustained load with faults coming and going — the
failure mode where slow leaks, counter drift, and half-reverted
faults hide.

## What was built

**`hugrgate/chaos/soak.py`** (new module, exported from
`hugrgate.chaos`):

- **`SoakConfig`** — `duration_s` (default 2.0, small by design),
  `target_ops_per_s`, `max_ops`, `invariant_every_n_ops`,
  `expected_errors` (type names); validated.
- **`ScheduledFault`** — name, `at_s`/`until_s`, `apply`/`revert`;
  validated (`0 <= at_s < until_s`).
- **`SoakRunner(workload, invariants, faults)`** — drives
  `workload(op_index)` at the target rate (paced, no catch-up
  spiral), applies/reverts faults on schedule, runs invariants
  periodically. Per-op exceptions counted by type name;
  invariant failures recorded as violations; the soak continues
  through both. **Faults are always reverted**, even mid-schedule
  — the runner never leaves a fault armed. Single-threaded and
  deterministic.
- **`SoakReport`** — ops, errors, unexpected errors (not in
  `expected_errors`), violations, faults applied, `passed`,
  JSON-serializable.

Pass criterion: no invariant violated and no *unexpected* error
type. Expected fault-induced errors (e.g. `BackendError` under an
armed `error_rate` fault) are counted, not failed.

## Verification

- 6 slow-marked tests (deselected by default): config/fault
  validation; clean 1s run (~40 ops, paced, values-in-spec
  invariant); scheduled `error_rate` fault mid-soak (fault
  fired, counted as expected, reverted afterward, soak passed);
  broken invariant detected with the soak continuing;
  unexpected error type flagged; `max_ops` stops the clock.
- `ruff check` clean; error-taxonomy, import-cycle, and
  API-inventory gates green. The inventory doc regenerated
  again via the sanctioned mechanism (soak module added).
