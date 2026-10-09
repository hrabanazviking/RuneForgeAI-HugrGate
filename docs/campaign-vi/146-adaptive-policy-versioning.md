# Slice 146 — Adaptive policy versioning

**Status:** complete. **Tests:** `tests/test_adaptive_versioning.py` — 13 tests green.

## What existed before

Checkpoints (slice 145) were anonymous snapshots — "which policy served
request X?" had no exact answer.

## What was built

`hugrgate/adaptive/versioning.py` — `AdaptivePolicyVersioning`:

- `create_version(state, parent_id, note)`: mints immutable `v<n>` with a
  SHA-256 digest of the canonical JSON state — telemetry's `policy_version`
  (slice 126) now resolves to exact bytes.
- `activate(version_id)`: single serving pointer; activations recorded.
- `lineage(version_id)`: parent chain to the root for audit.
- `verify(version_id, state)`: digest recomputation — the integrity check
  promotion flows use before trusting archived bytes (key order irrelevant:
  canonical JSON).
- Versions immutable: no "edit v3", only "mint v4 with v3 as parent".

## Integration

- Pairs with slice-145 checkpoints (anonymous snapshot → named release)
  and slice-126 telemetry (`policy_version` tags).

## Verification

- `pytest tests/test_adaptive_versioning.py` — 13/13 green: create/activate,
  lineage chains, content-addressed digests, key-order-insensitive verify,
  archive isolation (deep copies), activation history with previous pointer,
  unknown parent/version rejection, non-serializable rejection.
- `mypy hugrgate/adaptive` — clean.
