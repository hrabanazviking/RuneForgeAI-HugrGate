# Slice 438 — Project scaffolder

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_438_scaffold.py` (10 tests)

## What existed

Starting a HugrGate project meant assembling packaging, entry
points, and configs by hand.

## What changed

- `hugrgate/scaffold.py` (new): `scaffold_project(name, dir,
  force)` — validates the name (lowercase package-safe, not a
  keyword → `ScaffoldError`), refuses non-empty targets without
  `--force`, and writes the full tree: `pyproject.toml`,
  `README.md`, `.gitignore`, `spec.yaml`/`policy.yaml` (via the
  slice-437 generators, so they're valid), `state.example.yaml`,
  `src/<pkg>/main.py` (SDK v2 in-process decision), and
  `tests/test_smoke.py`.
- `hugrgate/cli.py`: `hugrgate new NAME [--dir] [--force]`.

## Verification

10 tests — and the proof is execution, not listing: the suite
scaffolds into a tmp dir, byte-compiles every generated file,
**runs the scaffolded project's own pytest suite in a
subprocess (1 passed)**, and runs `python -m demo.main`
end to end. Name validation (case, dashes, keywords),
non-empty-dir refusal, and CLI exit codes covered.
`ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_438_scaffold.py` — 10 passed
