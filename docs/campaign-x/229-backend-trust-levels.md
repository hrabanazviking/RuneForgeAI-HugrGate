# Slice 229 — Backend trust levels

**Date:** 2026-10-09 · **Tests:** `tests/test_privacy_trust.py` (12 tests)

## What existed

Trust was implicit: in-process = trusted, remote = untrusted, with
no way to distinguish a vetted EU-hosted inference endpoint under a
DPA from an unknown third-party API. The slice-226 trust floor for
`strict` data therefore blocked *all* unattested remotes — correct
but blunt.

## What changed

- New module `hugrgate/privacy_trust.py`:
  - `TrustAttestation` — operator-signed claim (level, attested_by,
    timestamps, expiry, note); unknown levels and past expiries
    rejected at construction.
  - `BackendTrustRegistry` — `attest` / `revoke` /
    `attestation_for` / `level_for` / `rank_for` / `meets`, plus
    `to_dict` / `from_dict`. Expired or revoked attestations fall
    back to the default level silently and safely (never upward).
  - Trust primitives (`TRUST_ORDER`, `trust_rank`,
    `default_trust_level`) moved here from `hugrgate.privacy` and
    re-exported there, avoiding an import cycle
    (`privacy_trust` must not import `privacy`).
- `PrivacyGuard` accepts `trust_registry=`; its class trust-floor
  checks now evaluate attested trust. Without a registry, slice-226
  defaults apply unchanged.

## Verification

- `pytest tests/test_privacy_trust.py` (+ 226/228 suites) — all green.
- Adversarial: expired attestation falls back to `basic`; wrong-name
  attestation doesn't leak to other backends; self-attested
  `enclave` still can't carry `forbidden`-class data remotely;
  revocation is idempotent.
- `ruff check` clean; no import cycle introduced.
