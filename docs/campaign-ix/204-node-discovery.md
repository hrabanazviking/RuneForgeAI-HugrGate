# Slice 204 — Node discovery

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_discovery.py` (13 tests)

## What existed before

Slices 201–203 gave nodes an envelope, an identity, and a
self-description — but no way to *find* each other. Discovery was an
empty concept.

## What was built

- `hugrgate/cluster/discovery.py`:
  - `PeerRecord`: validated peer (node_id, host, port, last_seen,
    optional capabilities, source adapter, tls flag); `address`
    renders the `http(s)://host:port` URL; staleness helpers.
  - `Discovery`: adapter ABC — subclass + `peers()`; `start`/`stop`
    no-ops for pull-style adapters; context-manager support.
  - `DiscoveryRegistry`: merges adapters thread-safely, dedups by
    node_id (newest `last_seen` wins), prunes stale records on read,
    never lists the local node, and isolates adapter failures (one
    exploding adapter cannot blind the rest).

## Roles

Skald: no discovery existed. Rúnhild: framework-not-mechanism —
adapters plug in (205/206 build on this). Eldra: forged stdlib-only.
Sólrún: 13 tests green (merge/dedup/prune/self-exclusion/fault
isolation/lifecycle). Védis: exports, taxonomy, arch-map, manifest,
inventory regenerated. Scribe: committed `feat(gjallarbu-204)`.

## Verification

`pytest tests/test_cluster_discovery.py` — 13 passed; ruff clean; mypy
clean.
