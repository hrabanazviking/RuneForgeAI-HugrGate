# Slice 209 — Encrypted transport

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_transport.py`
(14 tests, marked `slow`)

## What existed before

Slice 208 authenticated envelopes (HMAC proves *who* sent a message)
but everything crossed the wire in cleartext — decision states may
carry sensitive fields, and a passive observer could read them all.

## What was built

- `hugrgate/cluster/transport.py`:
  - `make_self_signed_cert(cert, key, hostname, days)`: mints via the
    system `openssl` CLI (no new Python dependency); key file lands at
    0600; half-written pairs impossible (temp files + atomic rename).
  - `TLSServer`: context manager running any ASGI app over TLS on
    loopback in a background thread (ephemeral port discovery);
    refuses non-loopback binds.
  - `trusted_context_for(cert)`: client `SSLContext` trusting
    *exactly* the self-signed cert (it is its own CA) — effective
    certificate pinning; hostname checking off because node identity
    is key-based (202), with the HMAC layer (208) authenticating the
    peer. Callers are reminded to pair it with
    `trust_env=False` (proxy env must never reroute cluster traffic).
  - `cert_fingerprint` / `verify_cert_fingerprint` /
    `fetch_server_fingerprint` (TOFU pinning helper).

## Bugs caught by tests

- The sandbox's exotic `NO_PROXY` entries (`[::1]`, `[fd8b:...]`)
  choke httpx's env parser — tests now use `trust_env=False`, the
  same rationale `HugrGateClient` documents.
- `ssl.PEM_cert_to_DER_cert` raises `ValueError`, not `SSLError`, on
  bad PEM — now caught and mapped to `SpecError`.

## Roles

Skald: 208 audited — auth without encryption. Rúnhild: TLS via
openssl+stdlib, pinning-by-CA, TOFU helper. Eldra: forged. Sólrún: 14
tests green (cert minting, TLS round-trip, RPC-over-TLS, plaintext
rejected, wrong-cert rejected, fingerprint match). Védis: exports,
taxonomy (slow), arch-map, manifest, inventory regenerated. Scribe:
committed `feat(gjallarbu-209)`.

## Verification

`pytest tests/test_cluster_transport.py` — 14 passed; ruff clean;
mypy clean.
