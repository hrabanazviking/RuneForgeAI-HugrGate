# Slice 214 — Node latency scoring

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_node_latency.py`
(14 tests)

## What existed before

Peers were scored on health alone (213); a healthy but glacial peer
looked identical to a fast one.

## What was built

- `hugrgate/cluster/node_latency.py` — `LatencyTracker`: per-peer RTT
  samples (bounded window), EWMA, p50/p95, and
  `score = min(1.0, target_ms / ewma)` mirroring the backend health
  monitor's latency factor. Thread-safe; unknown peers score 1.0.
- `hugrgate/cluster/node.py`: every node owns `node.latency`;
  `decide_remote()` measures round-trip time on success and records
  it; `refresh_scores()` pushes latency into the router alongside
  health.

## Roles

Skald: routing scores audited — no latency dimension. Rúnhild: EWMA +
target-relative scoring mirroring slice 17. Eldra: forged. Sólrún:
14 tests green (EWMA math, percentiles, validation, RPC timing,
slow peer sinks in routing). Védis: exports, taxonomy, arch-map,
manifest, inventory regenerated. Scribe: committed
`feat(gjallarbu-214)`.

## Verification

`pytest tests/test_cluster_node_latency.py` — 14 passed; ruff clean;
mypy clean.
