# Slice 476 — Feature freeze

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_476_freeze.py` (17 tests)

## What existed

No freeze machinery at all: `release/` did not exist, and nothing
stopped feature work from landing during the 1.0 run-up.

## What changed

- `hugrgate/gauntlet/freeze.py` (new): `FreezeManifest` /
  `ChangeRequest` / `FreezeVerdict` / `Waiver`, `load_manifest()`,
  `evaluate()`, `check_public_api_growth()`. Allowed kinds under the
  freeze: `bugfix`, `security`, `docs`, `tests`, `refactor`, `perf`.
  Anything else — or any public-API/dependency growth — needs a
  waiver recorded in the manifest.
- `release/freeze.toml` (new): the frozen version (`1.0.0rc1`),
  freeze date, allow-list, and an empty waiver table.

## Verification

`pytest tests/test_gauntlet_476_freeze.py` green; `ruff`/`mypy` clean
on the new module.
