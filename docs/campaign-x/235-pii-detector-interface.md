# Slice 235 — PII detector interface

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_pii.py` (19 tests)

## What existed

No PII detection: emails, SSNs, and credit-card numbers in state
were invisible to every privacy mechanism built so far.

## What changed

- New module `hugrgate/privacy_pii.py`:
  - `PIIDetector` — abstract interface (`scan_text` + free nested
    `scan_state`); custom detectors plug in by subclassing.
  - `RegexPIIDetector` — built-in kinds (email, phone, SSN, credit
    card, IPv4) with validators that cut false positives: Luhn
    check for cards, SSA area/group rules for SSNs, octet ranges
    for IPv4. Kinds are subsettable.
  - `CompositePIIDetector` — unions built-in and custom detectors.
  - `PIIScrubber` — mask/drop actions on state; mask replaces the
    whole value (`[PII:email,ssn]`) so residual structure can't aid
    re-identification.
  - Findings carry redacted previews only, never raw values.

## Verification

- `pytest tests/test_privacy_pii.py` — 19 passed.
- Adversarial: invalid SSN areas, Luhn-failing digit strings, and
  out-of-range IPv4 produce no findings; a custom employee-ID
  detector composes with the built-in one.
- `ruff check` clean.
