# Slice 212 — Distributed ladder routing

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_routing.py`
(19 tests)

## What existed before

Peers could be found (204-206), called (207), and trusted (208-209),
but nothing *chose* between them: routing was whoever the operator
hard-wired. The local ladder (`hugrgate.ladder`) knew nothing of nodes.

## What was built

- `hugrgate/cluster/routing.py`:
  - `PeerScores` — validated [0,1] health/latency/cost triple (fed by
    slices 213-215; defaults to perfect).
  - `DistributedRouter(node, weights)` — **filter → score → walk**:
    filters by capability advertisement, privacy boundary (211), and
    local backend support; scores by weighted mean; walks candidates
    best-first with local winning ties. `decide()` walks the ladder:
    `BackendError` → next candidate, `Abstention`/`PrivacyViolation`
    propagate (decisions, not transport failures); the winner is
    recorded in `result.metadata["route"]`. `audit()` explains a
    routing decision for logs.
- `hugrgate/cluster/node.py`: every node owns `node.router`.

## Roles

Skald: ladder + RPC audited — no node selection existed. Rúnhild:
filter/score/walk mirroring ladder semantics. Eldra: forged.
Sólrún: 19 tests green (ordering, weights, privacy/capability
filters, local→remote failover, abstention propagation,
no-route/all-failed errors). Védis: exports, taxonomy, arch-map,
manifest, inventory regenerated. Scribe: committed
`feat(gjallarbu-212)`.

## Verification

`pytest tests/test_cluster_routing.py` — 19 passed; ruff clean; mypy
clean.
