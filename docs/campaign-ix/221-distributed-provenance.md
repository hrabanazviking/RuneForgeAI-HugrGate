# Slice 221 — Distributed provenance

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_provenance_dist.py`
(15 tests)

## What existed before

`PROVENANCE_PULL/RESPONSE` existed in the protocol (201) but nothing
spoke them: every node's decision history was marooned locally, and
records carried no origin — a merged history couldn't say *who*
decided.

## What was built

- `hugrgate/cluster/provenance_dist.py`:
  - `attribute_record(record, node_id)` — stamps
    `metadata["node_id"]` with `setdefault`: origin is set once, never
    overwritten through merges.
  - `ProvenanceExchange(node)` — `serve_pull(since, limit)` (serving
    side, validates + clamps), `pull(peer, ...)` (validates every
    record shape via `DecisionRecord.from_dict`, attributes to the
    peer), `merge(records)` (idempotent dedup on
    `(request_hash, node_id)`; the local store re-chains merged
    records so `verify_chain()` still passes), `pull_and_merge`.
  - Records never carry raw states (only `state_keys`), so sharing is
    privacy-safe by construction.
- `hugrgate/cluster/node.py`: `node.provenance_exchange`,
  `handle_provenance_pull` (bad args → typed error envelope).
- `hugrgate/cluster/rpc.py`: `RPCClient.pull_provenance` (control-
  plane read: never shed, never quorum-gated).
- The exchange describes its node slice as a local `_ExchangeNode`
  Protocol — no `TYPE_CHECKING` import of node.py, keeping the gate's
  acyclic-import rule green.

## Roles

Skald: protocol audited — provenance types existed, no speakers, no
attribution. Rúnhild: attribute-at-pull + idempotent merge into the
re-chaining store. Eldra: forged. Sólrún: 15 tests green
(attribution stickiness, since/limit, idempotent merge, chain still
verifies, liar-peer rejection). Védis: exports, taxonomy, arch-map,
manifest, inventory regenerated. Scribe: committed
`feat(gjallarbu-221)`.

## Verification

`pytest tests/test_cluster_provenance_dist.py` — 15 passed; ruff
clean; mypy clean; import-cycle gate green.
