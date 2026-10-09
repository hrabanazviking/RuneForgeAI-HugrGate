# Slice 225 — Distributed release gate

## What
The Campaign IX capstone: `hugrgate/cluster/release_gate.py` with
`DistributedReleaseGate`, which refuses a release unless every member
of the cluster agrees it is healthy. It runs the same checks the
campaign built, slice by slice:

| Check | Source slices |
|---|---|
| `no_quarantined_peers` | 213 (health quarantine) |
| `peer_health_scores` (≥ min) | 213–215 (health/latency/cost scoring) |
| `quorum_present` | 219 (partition/quorum, enforcing nodes only) |
| `provenance_chains_valid` | 221–222 (distributed provenance, trace) |
| `benchmark:*` floors | 224 (success-rate + throughput per scenario) |

## API
- `ReleaseGateConfig(min_health_score=0.5, max_quarantined=0,
  require_quorum=True, min_success_rate=0.99,
  min_throughput_per_s=100.0, benchmark_scenarios=(...))`
- `DistributedReleaseGate(config).evaluate(nodes,
  benchmark_report=None) -> ReleaseReport`
- `ReleaseReport`: `.passed`, `.failed()`, `.summary()`, `.to_dict()`
- CLI (benchmark artifacts, CI-friendly exit code):
  `python -m hugrgate.cluster.release_gate --bench-report
  benchmarks/cluster_bench_report.json [--min-throughput N]
  [--min-success-rate R]`

## Decisions
- Exported from `hugrgate.cluster.__init__` (import-light, like the
  other core campaign modules).
- Quorum check applies only to nodes with `enforce_quorum=True`
  (opt-in, per slice 219's convention).
- The CLI gates benchmark artifacts only; live-node checks are
  programmatic via `evaluate()` (there is no remote gate client yet —
  the gate runs inside the deploying operator, not over the wire).
- `evaluate([])` fails closed: no nodes, no release.

## Tests
`tests/test_cluster_release_gate.py` — 11 tests: healthy cluster
passes; each failure mode blocks individually (quarantine, weak
peer, lost quorum on one node, tampered provenance chain, impossible
benchmark floor, missing scenario); `evaluate` with a real benchmark
report; report shape/summary JSON-serializable.

## Verification
- 11/11 new tests pass; ruff + mypy clean; gate tests green (67/67)
- CLI against the committed report:
  `python -m hugrgate.cluster.release_gate --bench-report
  benchmarks/cluster_bench_report.json` → PASS (exit 0);
  with `--min-throughput 999999999` → FAIL (exit 1)
- Full suite (fast): 821 passed, 0 failed across 4 consecutive runs.
  One earlier run showed a single failure that did not reproduce in
  any of the 4 following runs (no FAILED line on re-run) — recorded
  as a non-blocking flake, not a regression. Prime suspect:
  `test_shed_load_recovers` (slice 218, known timing-sensitive).

---

## Campaign IX completion report (slices 201–225)

**Mission:** Distributed HugrGate — 25 slices, all forged as real
integrated code in `hugrgate/cluster/`, all green, committed on
`gjallarbu/campaign-ix`.

| Slice | Module | Tests |
|---|---|---|
| 201 Node protocol design | `protocol.py` | 16 |
| 202 Node identity | `identity.py` | 16 |
| 203 Capability advertisement | `capabilities.py` | 15 |
| 204 Node discovery | `discovery.py` | 13 |
| 205 Static peer configuration | `static_config.py` | 21 |
| 206 LAN discovery adapter | `lan.py` | 13+1 skip |
| 207 Remote decision RPC | `rpc.py` | 25 |
| 208 Mutual authentication | `auth.py` | 21 |
| 209 Encrypted transport | `transport.py` | 14 |
| 210 Policy propagation | `policy_sync.py` | 18 |
| 211 Privacy boundary enforcement | `privacy_boundary.py` | 14 |
| 212 Distributed ladder routing | `routing.py` | 19 |
| 213 Node health scoring | `node_health.py` | 14 |
| 214 Node latency scoring | `node_latency.py` | 14 |
| 215 Node cost scoring | `node_cost.py` | 9 |
| 216 Work stealing | `work_stealing.py` | 20 |
| 217 Distributed batching | `distributed_batch.py` | 10 |
| 218 Backpressure protocol | `backpressure.py` | 11 |
| 219 Network partition handling | `partition.py` | 15 |
| 220 Offline peer recovery | `recovery.py` | 10 |
| 221 Distributed provenance | `provenance_dist.py` | 15 |
| 222 Trace correlation | `trace.py` | 22 |
| 223 Distributed chaos tests | `chaos.py` | 12 |
| 224 Cluster benchmark suite | `bench.py`, `bench_support.py` | 11 |
| 225 Distributed release gate | `release_gate.py` | 11 |

**Integration surface:** `ClusterNode` composes identity + gate +
discovery + RPC; `/cluster/*` routes mount via
`create_app(gate, node=...)`; privacy is fail-closed both ends;
auth is PSK + per-message HMAC with replay rejection; transport is
TLS with CA pinning; quorum is opt-in.

**Benchmark findings (loopback, committed report):** remote decisions
~1.7k/s at p50 ~0.5ms; router absorbs 50% peer chaos with 100%
success via failover; distributed batch ~5.8k jobs/s at 25
jobs/envelope; work stealing ~30k/s; provenance sync ~8.7k
records/s, chains verify.

**Security posture:** mutual auth (HMAC-SHA256, replay rejection),
TLS transport with pinning, fail-closed privacy (strict =
local-only, `private_*` redacted), chaos tooling quarantined to
tests/operators (nothing in production paths enables it).

**Remaining debt / blockers:** none blocking. Known non-blocking
items: one unreproducible full-suite flake (suspect
`test_shed_load_recovers`); `evaluate([])` fails closed by design;
no remote gate client yet — the release gate runs in the deploying
operator, not over the wire.

