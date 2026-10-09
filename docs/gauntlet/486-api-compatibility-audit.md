# Slice 486 — API compatibility audit

**Date:** 2026-10-09 · **Tests:** `tests/test_gauntlet_486_api_audit.py` (12 tests)

## What existed

The append-only surface policy (slice 003) was prose plus a
snapshot test; nothing classified drift as breaking vs additive,
and signature narrowings were invisible.

## What changed

- `hugrgate/gauntlet/api_audit.py` (new): `snapshot_package()`
  (every module's `__all__` → `{kind, sig}`), `save_baseline()` /
  `load_baseline()`, `signatures_compatible()` (AST-parsed
  signatures, no eval; new defaulted params OK, new required
  params / removed params / optional→required are breaking),
  `diff_snapshots()` → `ApiDiff` (added/removed modules & names,
  kind changes, signature changes; `breaking` / `additive`
  properties).
- `docs/gauntlet/api-baseline-1.0.json` (new): the 1.0 baseline —
  **422 modules, 2563 public names**, canonical JSON; the live
  tree diffs clean against it.

## Verification

`pytest tests/test_gauntlet_486_api_audit.py` green, including the
live-tree-vs-baseline diff (`no drift`); `ruff`/`mypy` clean.
