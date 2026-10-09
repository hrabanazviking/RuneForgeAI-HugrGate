# Slice 210 — Policy propagation

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_policy_sync.py`
(18 tests)

## What existed before

Every node applied only its own policy. A cluster could hold
contradictory safety postures — node A forbidding remote inference
while node B routed remote work under a permissive policy — with no
mechanism to converge.

## What was built

- `hugrgate/cluster/policy_sync.py`:
  - `PolicyVersion` — ordered `(version, timestamp, node_id)` stamp.
  - `merge_policies` — documented fail-closed semantic:
    **strictest-wins** for safety fields (`minimum_probability`→max,
    `remote_inference`→AND veto, `privacy_class`→strict-if-any,
    `maximum_latency_ms`/`max_cost`→min, `allowed_backends`→
    intersection, `fallback_behavior`→most conservative,
    `review_band`→envelope union); **newest-wins** for
    `preferred_backends`.
  - `PolicyPropagator` — versioned effective policy; `update()`
    (operator) bumps; `receive()` merges and reports change.
- `hugrgate/cluster/node.py`: every node owns a `PolicyPropagator`;
  `POLICY_PUSH`/`POLICY_PULL` handlers registered; `propagate_policy()`
  pushes to all known peers best-effort (one dead peer never blocks
  the rest).
- `hugrgate/cluster/rpc.py`: the outbound hook (208 signing) moved
  from `_prepare` into `send()` so *every* outbound envelope —
  decide, batch, policy, … — is sealed.

## Roles

Skald: 207's RPC audited — policy stayed local. Rúnhild: versioned
strictest-wins merge designed. Eldra: forged. Sólrún: 18 tests green
(merge symmetry, veto, newest-wins preferences, node handlers,
multi-peer propagation with a dead peer). Védis: exports, taxonomy,
arch-map, manifest, inventory regenerated; 207's tests re-green after
the hook refactor. Scribe: committed `feat(gjallarbu-210)`.

## Verification

`pytest tests/test_cluster_policy_sync.py` — 18 passed;
`pytest tests/test_cluster_rpc.py tests/test_cluster_auth.py` — 46
passed; ruff clean; mypy clean.
