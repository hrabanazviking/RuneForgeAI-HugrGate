# Slice 211 — Privacy boundary enforcement

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_privacy_boundary.py`
(14 tests)

## What existed before

The RPC checked `remote_inference` but had no *boundary* concept: a
peer's whole state crossed the wire unexamined, `privacy_class="strict"`
meant nothing distributed, and nothing distinguished sensitive fields.

## What was built

- `hugrgate/cluster/privacy_boundary.py` — `PrivacyBoundary`, the
  single choke point both ends consult:
  - `check_outbound_allowed(policy)`: raises `PrivacyViolation` unless
    `remote_inference=True`; `privacy_class="strict"` is **local-only**
    — state never leaves the node (fail-closed; strict-if-any wins in
    propagation, so one strict member locks the cluster's remote
    posture).
  - `redact_state()`: drops `private_*`-prefixed fields (plus an
    explicit per-call set); returns `(clean, dropped)` — the drop is
    reported, never silent, and the input is never mutated.
- `hugrgate/cluster/rpc.py`: `decide()`/`batch()` now
  `prepare_outbound()` every request — permission-checked, redacted,
  with `redacted_fields` in the payload; raw-dict batch policies are
  validated + checked instead of trusted.
- `hugrgate/cluster/node.py`: server side rejects `strict` policies
  (defense in depth) and records `redacted_fields` in result metadata.

## Roles

Skald: 207/210 audited — no boundary, strict meaningless remotely.
Rúnhild: allow-then-minimize choke point; strict=local-only.
Eldra: forged. Sólrún: 14 tests green (redaction reporting, strict
blocked both ends, per-item batch redaction, dict-policy checks).
Védis: exports, taxonomy, arch-map, manifest, inventory regenerated;
207/208/210 suites re-green. Scribe: committed `feat(gjallarbu-211)`.

## Verification

`pytest tests/test_cluster_privacy_boundary.py` — 14 passed; ruff
clean; mypy clean.
