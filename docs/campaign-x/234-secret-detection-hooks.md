# Slice 234 — Secret detection hooks

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_secrets.py` (23 tests)

## What existed

No secret scanning anywhere: a state dict containing an AWS key or
a PEM private key would flow to a remote backend, into the cache
key, and through provenance without a single check.

## What changed

- New module `hugrgate/privacy_secrets.py`:
  - `SecretScanner` — curated high-precision patterns (AWS access/
    secret keys, GitHub tokens/PATs, Slack tokens, PEM private keys,
    bearer tokens, credential assignments) plus an opt-in
    conservative high-entropy heuristic for opaque tokens.
  - `scan_text` / `scan_state` (nested, dotted paths, deduped);
    findings carry field, pattern, confidence, and a redacted
    preview (never the full secret).
  - `assert_no_secrets` raises `SecretDetected` with findings in
    details.
- New error `SecretDetected(PrivacyViolation)` in `hugrgate/errors.py`
  (code `secret_detected`, not recoverable), registered in
  `tests/test_errors.py`.
- `PrivacyGuard.check_no_secrets(state, scanner=None)` — hook point
  wired for the remote payload compiler (slice 237).

## Verification

- `pytest tests/test_privacy_secrets.py tests/test_errors.py` —
  35 passed.
- Adversarial: obfuscated credential assignments, secrets nested
  three levels deep, previews verified not to leak the secret.
- Documented boundary: the scanner catches accidents, not
  adversaries; entropy scan stays opt-in to avoid false positives.
- `ruff check` clean.
