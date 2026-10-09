# Slice 231 — Local-only field enforcement

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_localonly.py` (15 tests)

## What existed

Slice 227 introduced `local_only` marking on `FieldLabels`, but
nothing enforced it — a marked field would still flow to a remote
backend unless the caller remembered to filter.

## What changed

- New module `hugrgate/privacy_localonly.py`:
  - `LocalOnlyPolicy` (strip mode default, strict mode optional)
    and one-shot `enforce_local_only`.
  - Remote-bound state gets every present local-only field removed
    (nested-aware, emptied parents pruned); strict mode raises
    `LocalOnlyViolation` instead of stripping. Local destinations
    pass through untouched. Inputs are deep-copied, never mutated.
- New error `LocalOnlyViolation(PrivacyViolation)` in
  `hugrgate/errors.py` (code `local_only_violation`, not
  recoverable), registered in `tests/test_errors.py`.
- `PrivacyGuard.enforce_local_only(state, labels, backend,
  strict=...)` — enforcement available at the guard API.

## Verification

- `pytest tests/test_privacy_localonly.py` — 15 passed.
- Adversarial: deeply nested smuggled secrets caught via
  parent-path marking; strict mode gives a hard guarantee;
  non-mutation verified on nested inputs; sensitivity levels
  orthogonal to local-only marking.
- `ruff check` clean; no import cycle.
