# Slice 216 — Work stealing

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_work_stealing.py`
(20 tests)

## What existed before

`MessageType.STEAL_REQUEST/STEAL_RESPONSE` existed in the protocol
(201) but nothing spoke them: idle nodes sat idle while peers
queued work.

## What was built

- `hugrgate/cluster/work_stealing.py`:
  - `StealableQueue` — thread-safe double-ended queue of `StealJob`;
    local workers `take()` newest-first from the left, thieves
    `steal()` the oldest from the tail (Chase-Lev across the wire),
    capped at `MAX_STEAL_BATCH = 64`.
  - `StealJob` — serializable pending-decision job (spec/state/policy/
    context); `redacted()` strips `private_*` fields through the
    privacy boundary before any job crosses the wire.
- `hugrgate/cluster/node.py`: `node.steal_queue`,
  `handle_steal_request` victim handler (refuses when
  `serve_remote` is off, rejects bad `max_jobs`, reports `remaining`),
  `request_steal(peer, max_jobs)` thief side — enqueues stolen jobs
  locally and feeds health/latency monitors.
- `hugrgate/cluster/rpc.py`: `RPCClient.steal` — validates the
  victim's job shapes on arrival so a lying peer's garbage dies at
  the wire, not in the local queue.

## Roles

Skald: protocol audited — steal message types existed, no speakers.
Rúnhild: Chase-Lev semantics + privacy redaction + monitor feedback.
Eldra: forged. Sólrún: 20 tests green (ordering, caps, redaction,
refusal, end-to-end steal, monitor feeding, thread safety). Védis:
exports, taxonomy, arch-map, manifest, inventory regenerated. Scribe:
committed `feat(gjallarbu-216)`.

## Verification

`pytest tests/test_cluster_work_stealing.py` — 20 passed; ruff clean;
mypy clean.
