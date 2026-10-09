# Slice 242 — Encrypted provenance option

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_sealed.py` (15 tests)

## What existed

Provenance records were plaintext in memory: even `strict` /
`forbidden` records (redacted metadata) still exposed backend
names, values, probabilities, and chain structure to any memory
reader.

## What changed

- `hugrgate/privacy_provenance.py`: new `SealedProvenanceStore`
  (extends `PrivacyAwareProvenanceStore`):
  - Each record is chained over its canonical plaintext form,
    then pickled and sealed with `SealedBox`; the stored wrapper
    keeps chain hashes, `request_hash`, `timestamp`, and the
    `privacy_class` marker in plaintext (retention purges and
    link checks work without the key) while the body is opaque.
  - `verify_chain` checks outer links *and* unseals to verify
    inner content hashes — tampering fails closed.
  - `recent` / `by_hash` unseal (`SealError` on tamper);
    `purge` re-chains and re-seals survivors; `append_decision`
    still works in one call.
- `require_key` promoted to public in `hugrgate/privacy_crypto`.

## Verification

- `pytest tests/test_privacy_sealed.py` — 15 passed: opacity,
  chain verification, wrong-key/tamper fail-closed, purge
  re-chaining, eviction, namespace binding, and an adversarial
  plaintext-index forgery (detected).
- `mypy` and `ruff` clean.
