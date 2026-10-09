# Slice 483 — Dependency-minimum matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_483_depmin.py` (7 tests)

## What existed

`pyproject.toml` declared `pyyaml>=6.0` with no check that the
floor is installable or that the running environment meets it.

## What changed

- `hugrgate/gauntlet/deps.py` (new): `parse_requirement()`,
  `read_runtime_dependencies()`, numeric `version_key()` (no new
  dependency — `packaging` is not a HugrGate runtime dep),
  `installed_version()`, `check_minimums()` → `DepReport`,
  `render_min_requirements()` / `write_min_requirements()`.
- `tools/matrix/requirements-min.txt` (new, generated): the
  minimum-supported set (`pyyaml==6.0`); the test asserts the
  checked-in file byte-matches the generator.

## Verification

`pytest tests/test_gauntlet_483_depmin.py` green — the live env
(pyYAML 6.0.3) meets the floor; synthetic missing/too-old deps are
reported; `ruff`/`mypy` clean.
