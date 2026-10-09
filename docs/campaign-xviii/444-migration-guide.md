# Slice 444 — Migration guide

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_444_compat.py` (7 tests)

## What existed

`hugrgate/contracts/migration.py` had the dict-level machinery,
but no developer-facing entry point and no prose guide for the
three real migrations: v1 client → SDK v2, contract v1 → v2,
pre-protocol clients.

## What changed

- `hugrgate/compat.py` (new): `upgrade_client` rebuilds a v1
  client as `HugrGateSDK` with identical transport settings
  (lazy SDK import keeps httpx out of the base install);
  `migrate_contract` returns the v2 contract **with the real
  `MigrationReport`** (warnings/lossy preserved — the dict
  registry discards it).
- `docs/migration.md` (new): the three migrations, behavior
  changes to expect, and a rollout checklist.
- `hugrgate/loaders.py` (new): `load_spec`/`load_state`/
  `load_policy` extracted from `cli.py` (re-exported there),
  breaking the `cli ↔ inspect` import cycle the cycle test
  caught.
- `tests/test_dependency_rules.py`: `hugrgate.compat` joins
  SERVICE; `difflib/shlex/readline/keyword/py_compile`
  recognized as stdlib (campaign XVIII slices 435/436/438).

## Verification

7 tests green; `ruff`/`mypy` clean; `test_import_cycles` and
`test_dependency_rules` fully green again (15 passed); CLI +
inspect suites still green (52 passed).

## Commands run

- `pytest tests/test_deveco_444_compat.py` — 7 passed
- `pytest tests/test_import_cycles.py tests/test_dependency_rules.py` — 15 passed
