# Slice 218 — Backpressure protocol

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_backpressure.py`
(11 tests)

## What existed before

`QueueFull` (slice 007) existed for the daemon's local queue, but the
cluster had no admission control: a flooded node queued work until it
fell over, and a shed request was indistinguishable from any other
error on the wire.

## What was built

- `hugrgate/cluster/backpressure.py` — `AdmissionController`:
  token-bucket (burst `capacity`, sustained `refill_per_second`),
  `try_acquire()` / `retry_after_ms()` / `stats()`. Thread-safe.
- `hugrgate/cluster/node.py`: every node owns `node.admission`;
  `dispatch()` sheds work-plane messages (`decide/batch/steal
  _request`) with a typed `QueueFull` carrying `retry_after_ms` when
  no token is available. The control plane (heartbeats, policy,
  auth) is never shed — shedding the healing signal starts cascades.
- `hugrgate/cluster/routes.py`: `queue_full` envelopes become **HTTP
  429** with a `Retry-After` header (ceil of `retry_after_ms`).
- `hugrgate/cluster/rpc.py`: the client turns 429 back into
  `QueueFull` (recoverable) via the taxonomy registry, so callers can
  back off and retry.
- Anti-Checkbox Rule honored: the existing `QueueFull` taxonomy error
  was reused, not duplicated.

## Roles

Skald: cluster audited — no admission control anywhere. Rúnhild:
token bucket + 429 wire contract + control-plane exemption.
Eldra: forged. Sólrún: 11 tests green (bucket math, refill,
shedding, control-plane exemption, recovery, 429 round-trip both
directions). Védis: exports, taxonomy, arch-map, manifest, inventory
regenerated. Scribe: committed `feat(gjallarbu-218)`.

## Verification

`pytest tests/test_cluster_backpressure.py` — 11 passed; ruff clean;
mypy clean.
