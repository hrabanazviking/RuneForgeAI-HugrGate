# Slice 219 — Network partition handling

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_partition.py`
(15 tests)

## What existed before

`MessageType.HEARTBEAT` existed but had no handler — heartbeats went
nowhere, and no component asked whether the node could still see a
majority. A network split left both sides serving and routing remote
as if nothing had happened: split-brain by default.

## What was built

- `hugrgate/cluster/partition.py` — `PartitionDetector`:
  heartbeat-driven liveness (`note_heartbeat` / `is_live` /
  `last_seen`, staleness threshold, injectable clock), and
  `has_quorum(peer_ids)` = `(live + 1) * 2 > (known + 1)` (self counts
  on both sides; a lone node is its own majority; exactly half is not
  a majority). Thread-safe; `forget()` for clean leaves.
- `hugrgate/cluster/node.py`: every node owns `node.partition`;
  `HEARTBEAT` is now handled (records liveness, answers alive);
  `node.ping(peer)` heartbeats a peer and records it;
  `ClusterNode(..., enforce_quorum=False)` opts into fail-closed
  split-brain protection — without a visible majority the node
  refuses inbound work-plane messages (`BackendUnavailable`),
  routes local-only, and refuses direct `decide_remote` calls. Local
  decisions continue; only speaking *for the cluster* stops.
  `enforce_quorum` defaults off, following the codebase's convention
  (permissive defaults, explicit strictness like `require_auth`).
- `hugrgate/cluster/rpc.py`: `RPCClient.heartbeat(peer)` (control
  plane — never shed, never privacy-gated).
- Gate hardening found while verifying: `routing.py` and
  `distributed_batch.py` held `TYPE_CHECKING` imports of `node.py`
  while node.py imports them eagerly — an import cycle the AST-based
  gate counts. Both now describe the node slice they need as a local
  `Protocol` (`_RouterNode`, `_BatcherNode`), the same pattern slice
  208 used for auth. This also fixed a latent red gate reaching back
  to slice 212.

## Roles

Skald: heartbeat path audited — type existed, no handler, no quorum
question anywhere. Rúnhild: liveness + majority math + three fail-
closed gates (inbound, routing, direct RPC). Eldra: forged. Sólrún:
15 tests green (quorum math incl. exactly-half, staleness, all three
gates, default-off compat, ping end-to-end); full fast suite + gate
suite green after the cycle fix. Védis: exports, taxonomy, arch-map,
manifest, inventory regenerated. Scribe: committed
`feat(gjallarbu-219)`.

## Verification

`pytest tests/test_cluster_partition.py` — 15 passed; full fast
suite 731+ passed; gate suite green; ruff clean; mypy clean.
