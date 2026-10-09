# Slice 443 — Cookbook

**Date:** 2026-10-09 · **Tests:** `tests/test_deveco_443_cookbook.py` (8 tests, slow)

## What existed

Scattered examples and API docs, but no copy-paste recipes for
the first-hour tasks.

## What changed

- `docs/cookbook.md` (new): 6 self-contained recipes —
  five-line decide, abstention, review band, HTTP daemon + SDK,
  custom backend + conformance check, contract template
  validation — plus shared conventions.
- `tests/test_deveco_443_cookbook.py` (new, slow): extracts
  every ```python block and executes it in a fresh namespace;
  also asserts recipe count matches the `## N.` headings.

## Weaknesses the recipes found (fixed here)

- Recipe 2 assumed abstention is a *returned* value; `decide`
  actually *raises* `Abstention` — recipe now catches it.
- Recipe 5's sample backend hardcoded "log"/"escalate" and
  failed the conformance kit on generic specs; it now derives
  values from `spec.options`.

## Verification

8 passed. `ruff`/`mypy` clean.

## Commands run

- `pytest tests/test_deveco_443_cookbook.py` — 8 passed
