# Slice 023 — Test taxonomy rebuild

**Date:** 2026-10-09 · **Tests:** `tests/test_taxonomy.py` (3 tests)

## What the audit found

27 test files with no shared fixtures (every file redefined its own
stub backends and specs), no markers (no way to run "fast tests
only"), and no statement of what each file is *for*. The taxonomy is
now explicit and enforced.

## The taxonomy

| Category | Marker | Meaning | Files |
|---|---|---|---|
| unit | *(none)* | fast, single-component, no I/O | test_config, test_errors, test_foundation, test_logging, test_policy_invariants, test_provenance_integrity, test_resource_lifecycle, test_result_invariants, test_serialization_contracts, test_state_validation, test_backend_registry, test_coverage_attack, test_cluster_protocol, test_cluster_identity, test_cluster_capabilities, test_cluster_discovery, test_cluster_static_config |
| integration | `pytest.mark.integration` | multi-component behavior | test_ladder, test_deterministic, test_ml_calibration |
| slow | `pytest.mark.slow` | spawns servers/threads, sleeps | test_service, test_thread_safety, test_async_readiness |
| gate | `pytest.mark.gate` | meta-tests shelling out to tools | test_typecheck, test_static_analysis, test_arch_map, test_api_inventory, test_repo_truth, test_dependency_rules, test_import_cycles, test_package_boundaries, test_dead_code, test_determinism_contract, test_taxonomy, test_release_gate |

(`test_package_boundaries` is a gate: it runs a subprocess import
sweep. Unit is the default — no marker required.)

Useful selections: `pytest -m "not slow and not gate"` (378 fast
tests), `pytest -m gate` (58 tool-gate tests).

## Changes

- `tests/conftest.py`: shared fixtures — `cat_spec`, `binary_spec`,
  `policy`, `strict_policy`, `StubBackend` (deterministic,
  distribution-consistent), `stub_backend`, `gate_with_stub`.
- Markers registered in `[tool.pytest.ini_options]`; `pytestmark`
  applied per file per the table.
- `tests/test_taxonomy.py`: enforcement — every test module must
  carry a known category marker or be listed as unit in this doc's
  table; marked files must carry the matching `pytestmark`.

## Verification

Enforcement tests green; `ruff check` clean; collection works under
`-m` selections; full suite green.
