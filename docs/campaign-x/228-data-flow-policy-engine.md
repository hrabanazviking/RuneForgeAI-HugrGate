# Slice 228 — Data-flow policy engine

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_flow.py` (19 tests)

## What existed

No unified flow decision point: `PrivacyGuard` gated backends at
selection time, but the *rules* (class eligibility, trust, field
levels) lived in separate ad-hoc checks with no shared vocabulary,
no reasons, and no way to explain a denial.

## What changed

- New module `hugrgate/privacy_flow.py`:
  - `FlowRequest` — what flows where: privacy class, field
    sensitivity levels, local-only fields, destination name /
    remoteness / trust / jurisdiction, allowed jurisdictions.
  - `DataFlowPolicy` — ordered, deterministic rules: (1) class
    eligibility, (2) trust floor, (3) jurisdiction, (4) field
    levels, (5) local-only stripping. Deny mode raises
    `DataFlowDenied`; redact mode strips over-clearance and
    local-only fields instead. Hard rules always deny.
  - `FlowDecision` — `allow` / `redact` / `deny` with reasons and
    redaction lists; `raise_if_denied()` raises with details.
- New error `DataFlowDenied(PrivacyViolation)` in `hugrgate/errors.py`
  (code `data_flow_denied`, not recoverable), registered in
  `tests/test_errors.py` (import, code, recoverable, hierarchy,
  wire round-trip).

## Verification

- `pytest tests/test_privacy_flow.py tests/test_errors.py` — 31 passed.
- Adversarial: trust-downgrade/jurisdiction mismatch still denied,
  unknown class/sensitivity rejected, deterministic rule ordering
  verified (rule 1 reported before rule 2).
- `ruff check` clean.
