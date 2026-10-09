# Slice 202 — Node identity

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_identity.py` (16 tests)

## What existed before

Slice 201 defined the wire envelope with a `sender` field but no notion
of what a node id *is* — any 64-hex string would validate. No identity
generation, persistence, or secrecy model existed.

## What was built

- `hugrgate/cluster/identity.py`:
  - `NodeIdentity`: 256-bit secret (`secrets.token_bytes`), public
    `node_id = sha256(secret)` (64 hex). Secret never leaves the node;
    peers see only the id.
  - `generate()` mints from the OS CSPRNG; `save()`/`load()` persist as
    JSON with **0600 via `os.open`** (no world-readable race window);
    malformed files raise `SpecError`, never partial identities.
  - `to_advertisement()` — public face for discovery (id, display name,
    protocol version); unit-tested to never leak the secret.

## Roles

Skald: 201's envelope audited — sender ungrounded. Rúnhild: key→id
derivation chosen over raw UUIDs so ids are stable across restarts and
unforgeable without the key file. Eldra: forged stdlib-only
(`secrets`, `hashlib`, `os`). Sólrún: 16 tests green
(success/failure/boundary incl. 0600-permission assertion). Védis:
`__init__` exports extended; taxonomy/arch-map/manifest/inventory
regenerated. Scribe: committed `feat(gjallarbu-202)`.

## Verification

`pytest tests/test_cluster_identity.py` — 16 passed; ruff clean; mypy
clean.
