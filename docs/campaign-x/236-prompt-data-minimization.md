# Slice 236 — Prompt / data minimization

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_minimize.py` (15 tests)

## What existed

Outbound payloads carried the entire state mapping: whatever the
application put in `state` flowed to the backend, including debug
fields, credentials, and unrelated user data.

## What changed

- New module `hugrgate/privacy_minimize.py`:
  - `minimize_state(state, keep)` — projection to an explicit
    keep-list (top-level or dotted paths), nested-aware,
    non-mutating; returns `(minimized, MinimizationReport)`.
  - `MinimizationPolicy` — per-backend keep-lists with
    `declare`/`minimize` and dict round-trip; undeclared backends
    pass through unchanged (documented).
  - `PromptMinimizer` — renders minimized state into a compact
    prompt under a character budget; over-budget fields are skipped
    whole (recorded), never truncated mid-value.

## Verification

- `pytest tests/test_privacy_minimize.py` — 15 passed.
- Adversarial: 100 extra fields with a 2-field keep-list (only 2
  survive); dotted vs parent keep-list semantics pinned by test.
- `ruff check` clean.
