# Slice 220 — Offline peer recovery

**Date:** 2026-10-09 · **Tests:** `tests/test_cluster_recovery.py`
(10 tests)

## What existed before

A dark peer stayed dark in the monitors' memory forever: health
scores, latency, cost, and liveness all remembered only failures, and
nothing ever attempted a comeback — operators had to restart nodes to
clear the grudge.

## What was built

- `hugrgate/cluster/recovery.py` — `RecoveryManager`: exponential
  backoff per dark peer (`base * 2**(failures-1)`, capped),
  `should_retry` / `retry_after_s` / `mark_attempt` with an injectable
  clock, `dark_peers()`. Thread-safe.
- `hugrgate/cluster/node.py`:
  - every node owns `node.recovery`;
  - `decide_remote()` feeds it (failure lengthens backoff, success
    clears it) alongside health/latency;
  - `recover_peer(peer)` — the rejoin handshake: respects backoff
    (False when no retry is due), pings, and on success resets
    health/latency/cost/liveness/backoff for a true clean slate,
    re-pushes the cluster policy (210), returns True. Never raises —
    a failed handshake just lengthens the backoff.
  - `push_policy_to(peer)` extracted from `propagate_policy()` (now
    delegates; behavior unchanged) for the single-peer re-push.

## Roles

Skald: peer lifecycle audited — failure was forever, no comeback
path. Rúnhild: backoff + handshake + clean-slate reset.
Eldra: forged. Sólrún: 10 tests green (backoff math incl. cap,
retry timing, full monitor reset on rejoin, never-raises).
Védis: exports, taxonomy, arch-map, manifest, inventory regenerated.
Scribe: committed `feat(gjallarbu-220)`.

## Verification

`pytest tests/test_cluster_recovery.py` — 10 passed; ruff clean;
mypy clean.
