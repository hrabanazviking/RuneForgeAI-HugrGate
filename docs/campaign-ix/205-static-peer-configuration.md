# Slice 205 — Static peer configuration

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_static_config.py` (21 tests)

## What existed before

Slice 204 defined the discovery framework but shipped zero adapters —
a registry with nothing to merge. Fixed-membership clusters had no way
to declare peers.

## What was built

- `hugrgate/cluster/static_config.py`:
  - `load_static_config(path)`: JSON/YAML peer files, validated loudly
    — unknown keys (top-level and per-peer), bad ports, duplicate
    endpoints, malformed node ids, non-bool `tls` all raise
    `SpecError`. A typo never silently drops a peer.
  - `StaticPeerConfig.to_records()`: builds `PeerRecord`s; peers
    without a known `node_id` get a deterministic endpoint-derived
    placeholder, replaced on first authenticated contact (slice 208).
  - `StaticDiscovery`: pull-style `Discovery` adapter (incl.
    `from_file`); `example_config()` for operators.

## Roles

Skald: 204's registry audited — no adapters. Rúnhild: file format with
strict validation designed. Eldra: forged (`yaml` is a base
dependency). Sólrún: 21 tests green. Védis: exports, taxonomy,
arch-map, manifest, inventory regenerated. Scribe: committed
`feat(gjallarbu-205)`.

## Verification

`pytest tests/test_cluster_static_config.py` — 21 passed; ruff clean;
mypy clean.
