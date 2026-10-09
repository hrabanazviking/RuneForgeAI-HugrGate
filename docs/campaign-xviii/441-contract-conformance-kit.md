# Slice 441 — Contract conformance kit

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_441_contract_conformance.py` (10 tests)

## What existed

`lint_template` judged parameter hygiene; nothing systematically
exercised a template's *behavior* across its parameter space.

## What changed

- `hugrgate/contracts/conformance.py` (new):
  `run_template_conformance` — template shape, ERROR-clean
  lint, defaults instantiate, every allowed value instantiates,
  boundary values (rejection is conformant, crashes are not),
  unknown/wrong-type/missing-required parameters rejected with
  `ContractError`, seeded fuzz of 25 random instantiations;
  `run_contract_conformance` — instance battery (round-trip,
  lint-clean, `check_value` robust on garbage input);
  `assert_conformance` raises `ConformanceError`.
- `hugrgate/cli.py`: `hugrgate check-contract FILE`
  (`--instance` for a serialized contract), exit 1 on failure.
- Fixed `Path` missing import in cli.py (found by the new CLI
  tests).

## Verification

10 tests green; `ruff`/`mypy` clean. A deliberately broken
template (allowed value violating the ordinal ≥2-levels rule)
fails with a named check.

## Commands run

- `pytest tests/test_deveco_441_contract_conformance.py` — 10 passed
