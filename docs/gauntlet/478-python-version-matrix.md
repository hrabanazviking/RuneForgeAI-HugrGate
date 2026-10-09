# Slice 478 — Python-version matrix

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_478_pymatrix.py` (8 tests)

## What existed

`pyproject.toml` declared `requires-python = ">=3.10"` with no
machinery proving the claim — newer syntax could slip in unnoticed.

## What changed

- `hugrgate/gauntlet/pymatrix.py` (new): `SUPPORTED_MINORS =
  ((3,10),(3,11),(3,12),(3,13))`, `read_requires_python()`,
  `check_syntax_compat()` (parses every file with
  `ast.parse(feature_version=(3,10))`), `validate_matrix()`.
- `tools/matrix/python_matrix.py` (new, executable): runnable form,
  exit 0/1 with a report.

## Verification

`pytest tests/test_gauntlet_478_pymatrix.py` green; the tool run over
the repo reports **MATRIX OK — 418 files checked, 0 syntax
failures**; `ruff`/`mypy` clean.
