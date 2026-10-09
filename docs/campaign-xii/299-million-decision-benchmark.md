# Slice 299 — Million-decision benchmark

**Status:** complete. Commit: `feat(gjallarbu-299)` on `gjallarbu/campaign-xii`.

## Attack (what existed before)

No sustained-throughput measurement existed: benchmarks were
micro-scale (µs-level op timings). Nobody knew what the gate
sustains over 1M decisions — throughput, tail latency, or memory.

## What was built

- `hugrgate/millionbench.py` — new module:
  - `run_million(n, seed, state_pool_size, ...)`: n real
    `HugrGate.decide()` calls end to end (spec validation, backend
    routing, evaluation, result validation, provenance append).
  - `InstantBackend`: deterministic instant backend — measures the
    *pipeline*, not a model.
  - Seeded state pool (reproducible), warmup, systematic latency
    sampling (every 100th), RSS before/after, progress logging,
    error counting. `MillionResult.to_dict()`.
- `benchmarks/million_decisions.py` — the real 1M runner; artifact
  `benchmarks/million_decisions.json`.

## Real 1M run (this machine, 2026-10-09)

- **7,845 decisions/s**, 127.5s wall; p50 80.9µs, p95 134.0µs,
  p99 480.2µs, max 27.5ms; **0 errors**; RSS 27 → 1369 MB.

## Finding: unbounded provenance (attack result)

The RSS growth is `ProvenanceStore`: `HugrGate` appends a
deep-copied, hash-chained `DecisionRecord` per decision with **no
default bound** (~1.37 KB/decision → 1.3 GB per 1M). The store
*supports* `max_records` (with chain-preserving eviction via
`_floor_hash`) — the gate just doesn't use it. Measured follow-up
(200k decisions):

| provenance | throughput | memory |
|---|---|---|
| unbounded (default) | 6,543/s | +270 MB, grows forever |
| `max_records=10000` | **8,079/s (+23%)** | +0 MB, flat |

Bounding also wins throughput (less deepcopy/GC pressure). **Not
changed in this slice**: the unbounded default is audit behavior,
and silently evicting audit records is a product decision, not a
perf tweak. Recommended follow-up: a `provenance_max_records`
option on `HugrGate` (default bounded, opt-out to unbounded),
proposed to Volmarr — not snuck in.

## Baseline comparison

First sustained run at this scale — there is no prior baseline to
regress against. `benchmarks/million_decisions.json` **is** the
baseline for future campaigns; the slice-298 gate framework can
adopt a throughput gate from it.

## Tests

`tests/test_perf_299_millionbench.py` — 5 tests on small N (shape,
percentile ordering, zero errors, seed reproducibility, backend
contract, validation). All green; ruff clean; import-cycle gate
green. The 1M run itself is a manual script, not a test.
