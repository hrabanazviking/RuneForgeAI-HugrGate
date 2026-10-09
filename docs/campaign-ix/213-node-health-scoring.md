# Slice 213 — Node health scoring

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_node_health.py`
(14 tests)

## What existed before

The router (212) scored every peer a perfect 1.0 — a dead peer looked
exactly as attractive as a healthy one until a call failed, and
nothing remembered the failure.

## What was built

- `hugrgate/cluster/node_health.py` — `NodeHealthMonitor` (node-scope
  twin of the backend `HealthMonitor`): bounded outcome window per
  peer, `score = 1 - failures/window`, quarantine below threshold or
  after N consecutive failures, automatic healing on success,
  `reset()` for clean rejoins (slice 220). Thread-safe.
- `hugrgate/cluster/node.py`: every node owns `node.health`;
  `decide_remote()` records success/failure per RPC (only
  transport/backend failures count — abstention is a decision, not
  sickness); `refresh_scores()` pushes health into the router, so sick
  peers sink to the bottom of every route.

## Roles

Skald: 212's router audited — scores were all 1.0. Rúnhild: windowed
health + quarantine + healing, mirroring slice 17's backend monitor.
Eldra: forged. Sólrún: 14 tests green (quarantine triggers, gradual
healing, window bounds, RPC instrumentation, sick peer sinks in
routing). Védis: exports, taxonomy, arch-map, manifest, inventory
regenerated. Scribe: committed `feat(gjallarbu-213)`.

## Verification

`pytest tests/test_cluster_node_health.py` — 14 passed; ruff clean;
mypy clean.
