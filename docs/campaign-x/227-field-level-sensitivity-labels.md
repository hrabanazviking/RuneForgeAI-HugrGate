# Slice 227 — Field-level sensitivity labels

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_labels.py` (13 tests)

## What existed

Nothing field-level: the privacy class classified a whole decision,
but every field inside the state was treated identically. A single
secret field (an API key, an SSN) forced the entire payload to the
highest class or leaked.

## What changed

- New module `hugrgate/privacy_labels.py`:
  - `Sensitivity` — ordered `PUBLIC < INTERNAL < CONFIDENTIAL < SECRET`.
  - `FieldLabels` — per-field labels with dotted-path support for
    nested mappings; exact dotted labels beat parent labels; unlabeled
    fields fall back to a default. Fields can additionally be marked
    `local_only` (must never leave the process).
  - `filter_by_clearance(state, labels, clearance)` — returns a copy
    with above-clearance fields removed, applied recursively with
    empty mappings pruned; optionally drops local-only fields.
  - `to_dict` / `from_dict` round-trip for config persistence.
- Documented boundary (tested): a secret nested at an unlabeled
  deeper path inherits its parent's label — you must label the exact
  path you want to protect.

## Verification

- `pytest tests/test_privacy_labels.py` — 13 passed, including
  adversarial cases (nested-secret smuggling, input non-mutation,
  local-only dropping for remote consumers).
- `ruff check` clean.
