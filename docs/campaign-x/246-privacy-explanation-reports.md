# Slice 246 — Privacy explanation reports

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_explain.py` (11 tests)

## What existed

Privacy denials surfaced as bare error codes — actionable only
to someone who already knew the policy model. Operators needed
answers to "what happened, why, and what can I do".

## What changed

- New module `hugrgate/privacy_explain.py`:
  - `PrivacyExplainer.explain_denial(error, context=...)` —
    what happened / why the policy exists / what the operator
    can do, with per-code remediation templates and safe
    `{d[key]}` placeholder filling (unknown keys render as
    `(unknown)`, never crash).
  - `explain_dry_run(report)` — readable walkthrough of a
    dry-run report.
  - `explain_record(record)` — why a provenance record looks
    the way it does, derived from its real metadata
    (`redacted`, `state_keys`, `value_fingerprints`).
  - Remediation advice is advisory: every suggestion goes
    *through* the policy, never around it.

## Verification

- `pytest tests/test_privacy_explain.py` — 11 passed (every
  known code, unknown-code fallback, placeholder safety,
  dry-run walkthroughs, record explanations that never leak
  values).
- `mypy` and `ruff` clean; no import cycles.
