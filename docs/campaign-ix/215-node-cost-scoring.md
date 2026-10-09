# Slice 215 — Node cost scoring

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_node_cost.py`
(9 tests)

## What existed before

Peers were scored on health and latency only — a peer that charged
for every decision looked as cheap as a free one.

## What was built

- `hugrgate/cluster/node_cost.py` — `CostModel`: operator-set cost
  per decision per peer, `score = 1/(1+cost)` (preference, not veto),
  `affordable(node_id, max_cost)` budget gate. Unknown cost = 0.0
  (fail-closed: exclusion requires evidence). Thread-safe.
- `hugrgate/cluster/routing.py`: the router's `_peer_allowed` gains a
  **budget veto** — when `DecisionPolicy.max_cost` is set, peers whose
  cost exceeds it are excluded from routing entirely.
- `hugrgate/cluster/node.py`: every node owns `node.costs` (created
  before the router so routing can read it); `refresh_scores()` now
  pushes all three dimensions — health, latency, cost — into the
  router.

## Roles

Skald: routing audited — no cost dimension. Rúnhild: scoring as
preference + budget as veto, mirroring `policy.max_cost` semantics.
Eldra: forged. Sólrún: 9 tests green (score math, budget veto, no
exclusion without evidence, cost ordering); all 56 cluster-scoring
tests green. Védis: exports, taxonomy, arch-map, manifest, inventory
regenerated. Scribe: committed `feat(gjallarbu-215)`.

## Verification

`pytest tests/test_cluster_node_cost.py` — 9 passed; ruff clean;
mypy clean.
