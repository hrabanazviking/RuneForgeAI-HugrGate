# Slice 020 — Package boundary cleanup

**Date:** 2026-10-09 · **Tests:** `tests/test_package_boundaries.py` (4 tests)

## What the audit found

Five internal modules imported public names from the package root
(`from hugrgate import DecisionSpec, ...` in `bench`, `cli`,
`client`, `daemon`, `server`, plus a function-local one in
`cmd_decide`). It works today only because `__init__` happens to
import those names first — a latent partial-initialization cycle the
moment `__init__` grows (e.g. ever exporting `client` or `daemon`).

## Changes

- All internal root imports rewritten to their defining modules
  (`hugrgate.spec`, `hugrgate.result`, `hugrgate.policy`,
  `hugrgate.backend`, `hugrgate.core`, `hugrgate.errors`).
  `from hugrgate import __version__` remains the single sanctioned
  root import inside the package.
- Regenerated `docs/campaign-i/architecture-map.md` (import graph
  now shows the direct edges; 153 edges).
- New boundary tests: AST scan forbidding root-name imports in
  submodules; `__all__` pinned to the curated 16-name surface; every
  submodule importable standalone in a fresh interpreter.

## Verification

4 new tests green; full suite 493 passed; mypy clean; arch-map
freshness test green after regeneration.
