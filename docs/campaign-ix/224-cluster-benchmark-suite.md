# Slice 224 — Cluster benchmark suite

## What
A loopback-only benchmark suite for the distributed machinery,
`hugrgate/cluster/bench.py` (`run_cluster_benchmark` /
`python -m hugrgate.cluster.bench`), with five seeded scenarios and a
JSON report shaped like the existing `hugrgate/bench.py` artifact.

## Modules
- `hugrgate/cluster/bench.py` — `ClusterBenchConfig`, scenario
  functions, `run_cluster_benchmark`, CLI (`--out`, `--items`,
  `--scenarios`).
- `hugrgate/cluster/bench_support.py` — `LoopbackCluster` harness:
  N nodes wired loopback-to-loopback via a port router, per-node
  request counting, hot-swappable transports (for `ChaosProxy`),
  sized admission buckets (benchmarks are load generators).
  Also `percent_str`.

## Scenarios
| Scenario | What it measures |
|---|---|
| `remote_decide` | N `decide_remote` calls: p50/p95/mean latency, throughput |
| `router_failover` | 2 peers, first drops 50% (seeded chaos): success rate, failover split |
| `distributed_batch` | N jobs across 2 peers: envelopes sent, jobs/envelope, throughput |
| `work_steal` | victim queues N jobs, thief steals: steal throughput |
| `provenance_sync` | pull+merge N records: records/s, chain validity |

## Report
`benchmarks/cluster_bench_report.json` (200 items/scenario, checksum
recorded in `benchmarks/CHECKSUMS.sha256`). Current numbers on this
sandbox (loopback, no network):

| Scenario | Throughput |
|---|---|
| remote_decide | ~1.7k decisions/s, p50 ~0.5ms |
| router_failover | ~1.9k decisions/s, 100% success with 50% chaos on first peer |
| distributed_batch | ~5.8k jobs/s, 25 jobs/envelope |
| work_steal | ~30k steals/s |
| provenance_sync | ~8.7k records/s, chain valid |

## Decisions
- Kept out of `hugrgate/cluster/__init__.py` exports per the package's
  stated policy (routes/bench stay behind their own imports).
- Report pins `hugrgate_version`, `generated_at`, `platform`,
  config (incl. chaos seed) — same shape as `hugrgate/bench.py`.
- Benchmarks trip the backpressure bucket at full speed (by design);
  the harness sizes admission generously instead of retesting 218.
- `provenance_sync` passes `limit=n_items` — the default pull limit
  (100) would under-report by capping the merge.

## Artifacts
- `hugrgate/cluster/bench.py`, `hugrgate/cluster/bench_support.py`
- `tests/test_cluster_bench.py` (11 tests, fast)
- `benchmarks/cluster_bench_report.json` + CHECKSUMS entry
- Registered in test-taxonomy doc (unit/fast) and arch-map cluster layer

## Verification
- 11/11 new tests pass; ruff + mypy clean
- `test_dataset_checksums` passes with the new artifact
- CLI end-to-end: `python -m hugrgate.cluster.bench --out ... --items 200`
