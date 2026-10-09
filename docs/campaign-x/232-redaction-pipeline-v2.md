# Slice 232 — Redaction pipeline v2

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_redact.py` (21 tests)

## What existed

Slice-40 redaction was shallow: `redact_state` masked whole values
with a fixed string and `redact_record` dropped three top-level
metadata keys. Nested state (`{"debug": {"state": {...}}}` inside
metadata) and secrets embedded in longer strings sailed through
untouched.

## What changed

- New module `hugrgate/privacy_redact.py`:
  - `Redactor` strategies: `MaskRedactor` (full or partial),
    `PatternRedactor` (regexes over strings at any depth),
    `HashRedactor` (salted, field-bound, deterministic),
    `DropRedactor`, `TokenRedactor` (duck-typed vault, slice 233).
  - `RedactionPipeline`: per-field redactors (dotted paths),
    per-`Sensitivity` level strategies via `apply_with_labels`,
    free-text scrubbing; returns `(redacted, [(field, strategy)])`.
  - `redact_metadata` / `redact_record_deep`: deep scrub of
    provenance metadata — state keys dropped at any depth,
    strings pattern-scrubbed, `redacted: True`, idempotent.
- `PrivacyGuard.redact_record` now uses the deep scrub (superset of
  the old behavior; slice-40 tests still pass).

## Verification

- `pytest tests/test_privacy_redact.py` — 21 passed; `test_ladder.py`
  (62) still green, confirming the hardened `redact_record` is
  backward compatible.
- Adversarial: nested state smuggled in metadata removed;
  API-key-shaped secret inside a log line scrubbed; hash
  field-binding prevents cross-field joins.
- `ruff check` clean.
