# Slice 230 — Jurisdiction metadata

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_jurisdiction.py` (12 tests)

## What existed

Backends had no notion of *where* they process data. A remote
backend could silently sit in any jurisdiction, and there was no
operator control over cross-border data flows.

## What changed

- New module `hugrgate/privacy_jurisdiction.py`:
  - `JurisdictionRegistry` — backend name → jurisdiction code.
    Unlisted local backends default to `"local"`; unlisted remote
    backends default to `"unknown"`, which never matches an allowed
    set (fail closed).
  - `JurisdictionPolicy` — allowed-jurisdiction set (`None` = no
    restriction); `check(backend)` raises `JurisdictionViolation`.
    Local backends always pass.
  - Both serialize via `to_dict` / `from_dict`.
- New error `JurisdictionViolation(PrivacyViolation)` in
  `hugrgate/errors.py` (code `jurisdiction_violation`, not
  recoverable), registered in `tests/test_errors.py`.
- `PrivacyGuard` accepts `jurisdiction_registry=` and
  `jurisdictions_allowed=`; enforced in `remote_allowed`,
  `check_backend` (raises `JurisdictionViolation`), and therefore
  `filter_backends`.

## Verification

- `pytest tests/test_privacy_jurisdiction.py tests/test_errors.py` —
  24 passed.
- Adversarial: undeclared remotes denied under an allow-set (fail
  closed); local backends pass any allow-set; violation wire
  round-trips to the exact class.
- `ruff check` clean; no import cycle.
