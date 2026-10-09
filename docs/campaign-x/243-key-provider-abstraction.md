# Slice 243 — Key-provider abstraction

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_keys.py` (19 tests)

## What existed

Encryption (slices 241-242) took raw key bytes with no story for
where keys come from, how they rotate, or how one master key
serves multiple consumers safely.

## What changed

- New module `hugrgate/privacy_keys.py`:
  - `KeyProvider` interface (`get_key`, `key_ids`, `forget`).
  - `EnvKeyProvider` (hex/base64 env vars, optional prefix),
    `FileKeyProvider` (`<dir>/<id>.key`, warns on permissive
    modes, rejects path traversal), `EphemeralKeyProvider`
    (in-memory CSPRNG), `RotatingKeyProvider` (primary +
    retired; encryption uses primary, decryption tries all).
  - `derive_key` — HKDF per-context subkeys, so one master key
    serves cache/provenance/vault namespaces separately.
  - `cache_from_provider` / `provenance_store_from_provider` —
    one-call encrypted cache/store construction.
- New error `KeyProviderError(HugrGateError)` (code
  `key_provider_error`, not recoverable), registered in
  `tests/test_errors.py`.
- `tests/test_dependency_rules.py`: added `base64`, `binascii` to
  the `_STDLIB` allowlist (stdlib, not third-party).

## Verification

- `pytest tests/test_privacy_keys.py` — 19 passed (rotation,
  derivation separation, permissive-mode warning, traversal
  rejection, provider-built cache/store round-trips).
- `mypy` and `ruff` clean; dependency-rules gate green.
