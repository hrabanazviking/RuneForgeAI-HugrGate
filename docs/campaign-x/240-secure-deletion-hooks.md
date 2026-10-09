# Slice 240 — Secure deletion hooks

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_deletion.py` (12 tests)

## What existed

`purge_expired` (slice 239) removed records but did nothing about
the secrets inside them: bytearrays in metadata stayed in memory,
and there was no proof of deletion.

## What changed

- New module `hugrgate/privacy_deletion.py`:
  - `shred_bytes` — multi-pass in-place overwrite of `bytearray`
    (rejects immutable `str`/`bytes` loudly — shredding those is a
    caller bug); `SecureBuffer` context manager shreds on exit,
    even on exception.
  - `SecureDeleter` — hook registry + best-effort shred of
    bytearray values in record metadata; returns a
    `DeletionReceipt` (record hash, hooks fired, shredded fields).
    Attaches as `on_purge` to `purge_expired`.
  - `CryptoShredder` — key-destruction deletion for encrypted
    stores (drop the key, ciphertext becomes unreadable).
- Documented honesty boundary: overwriting reduces secret lifetime
  but cannot defeat interpreter/OS/hardware copies; crypto-shredding
  is the stronger primitive for high-sensitivity stores.

## Verification

- `pytest tests/test_privacy_deletion.py` — 12 passed, including
  end-to-end `purge_expired` + `SecureDeleter` with receipt, and an
  adversarial failing-hook case (exceptions propagate, never
  silently swallowed).
- `ruff check` clean.
