# Slice 241 — Encrypted cache option

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_crypto.py` (25 tests)

## What existed

The decision cache stored plaintext `DecisionResult` objects in
memory. Any process-memory reader (or a swap file) saw decisions in
the clear, and there was no cryptographic primitive anywhere in the
privacy stack.

## What changed

- New module `hugrgate/privacy_crypto.py`:
  - `hkdf` — HKDF-SHA256 (RFC 5869, verified against the spec's
    test vector).
  - `SealedBox` — stdlib-only authenticated encryption
    (HMAC-SHA256 counter-mode keystream + HMAC tag, random nonce
    per message, constant-time verification). Tampering, wrong
    keys, truncation, and associated-data mismatch raise
    `SealError`.
  - `EncryptedDecisionCache(DecisionCache)` — entries are pickled
    and sealed before storage; privacy-class cache rules still
    apply first; retention TTL caps honored; key rotation /
    tampering fails closed; deepcopy of the cache refused (never
    duplicate key material accidentally).
- New error `SealError(HugrGateError)` (code `seal_error`, not
  recoverable, carries `reason`), registered in
  `tests/test_errors.py`.

## Verification

- `pytest tests/test_privacy_crypto.py tests/test_errors.py` —
  37 passed, including bit-flip/tag-flip/truncation attacks,
  cross-namespace replay, and pickle round-trip fidelity.
- `mypy` clean on the new module; `ruff check` clean.
- Documented boundary: small auditable construction, not a
  libsodium replacement; protects at-rest data, not key holders.
