# Slice 217 — Distributed batching

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_distributed_batch.py`
(10 tests)

## What existed before

`RPCClient.batch` (207) could send several decisions in one envelope,
but callers had to group, chunk, and map results by hand — one ad-hoc
loop per call site, with no shared error semantics.

## What was built

- `hugrgate/cluster/distributed_batch.py`:
  - `DistributedBatcher(node, max_batch_size=32)` — `submit(node_id,
    BatchJob)` buffers jobs keyed by destination node; `flush()`
    sends one `BATCH_REQUEST` envelope per peer, chunked at
    `max_batch_size`, and returns `{node_id: [BatchOutcome, ...]}` in
    submit order.
  - `BatchOutcome` — per-job `ok` / `result` / `error` / `abstained`.
  - Fail-closed semantics: a failed peer poisons only its own jobs
    (explicit error outcomes); unknown peers, short replies, and
    malformed items all become error outcomes — no job ever vanishes
    silently. Jobs whose own policy forbids remote inference never
    leave the node (error outcome, zero wire bytes).
- `hugrgate/cluster/node.py`: every node owns `node.batcher`.

## Roles

Skald: batch wire audited — grouping was call-site ad-hoc. Rúnhild:
buffer/group/chunk/flush with explicit per-job outcomes. Eldra:
forged. Sólrún: 10 tests green (one-envelope-per-peer, chunking,
poison isolation, local-only jobs never sent, abstention mapping).
Védis: exports, taxonomy, arch-map, manifest, inventory regenerated.
Scribe: committed `feat(gjallarbu-217)`.

## Verification

`pytest tests/test_cluster_distributed_batch.py` — 10 passed; ruff
clean; mypy clean.
