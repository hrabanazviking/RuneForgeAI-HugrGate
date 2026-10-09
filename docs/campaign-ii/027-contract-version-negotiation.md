# Slice 027 — Contract version negotiation

## What existed before
- `is_supported_version()` / schema-version gating in `from_dict` (slice 026):
  a contract with an unsupported version is *rejected*, but two parties had
  no way to *agree* on a mutually supported version.

## What changed
- **`hugrgate/contracts/negotiation.py`** (new):
  - `VersionOffer(party, versions)` — one party's ordered offer
    (most-preferred first); validates non-empty party, unique well-formed
    `major.minor[.patch]` versions.
  - `negotiate_version(*offers) -> NegotiationResult` — agrees on one version.
    Selection: among versions supported by *every* party, minimize the sum
    of preference ranks (Borda-style, symmetric — no party privileged);
    ties break toward the highest version. Deterministic.
  - `ContractEndpoint(party, schema_versions, kinds)` — what one party
    brings to a session; `ContractEndpoint.local(kinds)` builds an endpoint
    for this codebase; `.offer()` derives its `VersionOffer`.
  - `negotiate_session(client, server) -> SessionAgreement` — full session:
    version via `negotiate_version`, kinds = intersection in client
    preference order; explicitly rejects a negotiated version this codebase
    cannot read (`negotiated_version_unreadable`).
  - Loud failures, never silent downgrades: `no_common_version`,
    `no_common_kind`, `duplicate_parties`, `malformed_version`, etc.
    (instance codes in `details["code"]` per the slice-10 taxonomy).
- **`hugrgate/contracts/__init__.py`**: exposes the `negotiation` submodule.
- **`tools/gen_arch_map.py`**: `hugrgate.contracts.negotiation` added to the
  `contract-engine` layer; machine docs regenerated.

## Design decisions
- Rank-sum minimization chosen over "highest common version" so a party that
  *prefers* an older stable version is heard; version height only breaks ties.
- Kind intersection follows *client* preference order (the consumer's ranking
  decides presentation order; the set itself is symmetric).

## Tests
- `tests/test_contracts_027.py`: 21 tests — happy paths (single party,
  identical offers, 3-party), rank-sum vs. version-height tie-breaks, patch
  ordering, session kind intersection order, and every failure mode
  (disjoint versions/kinds, no offers, duplicate parties, malformed/empty/
  duplicate versions, unreadable negotiated version).
- Full suite green (run at commit).

## Evidence
- `hugrgate/contracts/negotiation.py`, `tests/test_contracts_027.py`,
  regenerated campaign-i machine docs.
