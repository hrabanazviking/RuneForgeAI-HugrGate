# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T13:47:15.598164+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 69 Python files under `hugrgate/`
- **Total LOC:** 12946
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_async_readiness.py, test_backend_registry.py, test_cluster_auth.py, test_cluster_backpressure.py, test_cluster_capabilities.py, test_cluster_discovery.py, test_cluster_distributed_batch.py, test_cluster_identity.py, test_cluster_lan.py, test_cluster_node_cost.py, test_cluster_node_health.py, test_cluster_node_latency.py, test_cluster_partition.py, test_cluster_policy_sync.py, test_cluster_privacy_boundary.py, test_cluster_protocol.py, test_cluster_provenance_dist.py, test_cluster_recovery.py, test_cluster_routing.py, test_cluster_rpc.py, test_cluster_static_config.py, test_cluster_trace.py, test_cluster_transport.py, test_cluster_work_stealing.py, test_config.py, test_coverage_attack.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_errors.py, test_foundation.py, test_import_cycles.py, test_ladder.py, test_logging.py, test_ml_calibration.py, test_package_boundaries.py, test_policy_invariants.py, test_provenance_integrity.py, test_release_gate.py, test_repo_truth.py, test_resource_lifecycle.py, test_result_invariants.py, test_serialization_contracts.py, test_service.py, test_state_validation.py, test_static_analysis.py, test_taxonomy.py, test_thread_safety.py, test_typecheck.py

## Module table

| Module | LOC | Docstring | Internal imports |
|---|---|---|---|
| `hugrgate.__init__` | 43 | HugrGate — local-first, model-agnostic probabilistic decision runtime. | hugrgate |
| `hugrgate.abstain` | 111 | Abstention — typed "I don't know" results and review banding. Slice 15. | hugrgate |
| `hugrgate.backend` | 151 | Backend interface + registry. Slice 6. | hugrgate |
| `hugrgate.backends.boosting` | 69 | Gradient boosting backend. Slice 24. | hugrgate |
| `hugrgate.backends.embedding` | 260 | Embedding backend — prototype classifier. Slice 33. | hugrgate |
| `hugrgate.backends.forest` | 74 | Random forest backend. Slice 23. | hugrgate |
| `hugrgate.backends.llm` | 247 | Local LLM backend — constrained decoding. Slice 35. | hugrgate |
| `hugrgate.backends.logreg` | 304 | Logistic regression backend. Slice 22. | hugrgate |
| `hugrgate.backends.nli` | 153 | NLI backend — statement entailment as a binary decision. Slice 34. | hugrgate |
| `hugrgate.backends.rules` | 381 | Rule backend — predicates, decision tables, confidence distributions. | hugrgate |
| `hugrgate.bench` | 345 | Benchmark harness — datasets → backends → metrics. Slice 45. | hugrgate |
| `hugrgate.bench_report` | 146 | Benchmark report — markdown rendering of benchmark JSON. Slice 47. | — |
| `hugrgate.cache` | 181 | Decision cache — request-hash keyed result memoization. Slice 38. | hugrgate |
| `hugrgate.calibration.__init__` | 47 | Probability calibration package. Slices 26-29. | hugrgate |
| `hugrgate.calibration._base` | 121 | Calibration base classes (private). | hugrgate |
| `hugrgate.calibration.isotonic` | 112 | Isotonic regression via the Pool Adjacent Violators (PAV) algorithm. | hugrgate |
| `hugrgate.calibration.metrics` | 149 | Calibration metrics. Slice 28. | hugrgate |
| `hugrgate.calibration.platt` | 131 | Platt scaling. Slice 26. | hugrgate |
| `hugrgate.calibration.profiles` | 264 | Calibration profiles. Slice 29. | hugrgate |
| `hugrgate.calibration.temperature` | 137 | Temperature scaling. Slice 27. | hugrgate |
| `hugrgate.circuit` | 174 | Circuit breaker — per-backend failure containment. Slice 18. | hugrgate |
| `hugrgate.cli` | 277 | HugrGate command-line interface. Slice 44. | hugrgate |
| `hugrgate.client` | 220 | HugrGate Python SDK — client for the HTTP service. Slice 43. | hugrgate |
| `hugrgate.cluster.__init__` | 208 | Cluster package for distributed HugrGate. Campaign IX (slices 201-225). | hugrgate |
| `hugrgate.cluster.auth` | 155 | Mutual authentication for cluster RPC. Slice 208. | hugrgate |
| `hugrgate.cluster.backpressure` | 103 | Backpressure protocol. Slice 218. | hugrgate |
| `hugrgate.cluster.capabilities` | 168 | Node capability advertisement. Slice 203. | hugrgate |
| `hugrgate.cluster.discovery` | 175 | Node discovery — finding peers. Slice 204. | hugrgate |
| `hugrgate.cluster.distributed_batch` | 211 | Distributed batching. Slice 217. | hugrgate |
| `hugrgate.cluster.identity` | 123 | Node identity — stable, unforgeable node ids. Slice 202. | hugrgate |
| `hugrgate.cluster.lan` | 286 | LAN discovery adapter — UDP multicast HELLOs. Slice 206. | hugrgate |
| `hugrgate.cluster.node` | 680 | ClusterNode — one HugrGate node in a cluster. Slice 207 (grows). | hugrgate |
| `hugrgate.cluster.node_cost` | 70 | Node cost scoring. Slice 215. | hugrgate |
| `hugrgate.cluster.node_health` | 144 | Node health scoring. Slice 213. | hugrgate |
| `hugrgate.cluster.node_latency` | 133 | Node latency scoring. Slice 214. | hugrgate |
| `hugrgate.cluster.partition` | 98 | Network partition handling. Slice 219. | hugrgate |
| `hugrgate.cluster.policy_sync` | 189 | Policy propagation across the cluster. Slice 210. | hugrgate |
| `hugrgate.cluster.privacy_boundary` | 96 | Privacy boundary enforcement. Slice 211. | hugrgate |
| `hugrgate.cluster.protocol` | 196 | Gjallarbrú node wire protocol. Slice 201. | hugrgate |
| `hugrgate.cluster.provenance_dist` | 139 | Distributed provenance. Slice 221. | hugrgate |
| `hugrgate.cluster.recovery` | 103 | Offline peer recovery. Slice 220. | hugrgate |
| `hugrgate.cluster.routes` | 99 | Cluster HTTP routes — ``/cluster/*``. Slice 207. | hugrgate |
| `hugrgate.cluster.routing` | 255 | Distributed ladder routing. Slice 212. | hugrgate |
| `hugrgate.cluster.rpc` | 483 | Remote decision RPC. Slice 207. | hugrgate |
| `hugrgate.cluster.static_config` | 182 | Static peer configuration. Slice 205. | hugrgate |
| `hugrgate.cluster.trace` | 247 | Trace correlation. Slice 222. | hugrgate |
| `hugrgate.cluster.transport` | 235 | Encrypted transport for cluster RPC. Slice 209. | hugrgate |
| `hugrgate.cluster.work_stealing` | 127 | Work stealing. Slice 216. | hugrgate |
| `hugrgate.core` | 159 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 502 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 154 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
| `hugrgate.fallback` | 171 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 291 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 140 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 321 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.log` | 101 | Structured logging for HugrGate (slice 009). | — |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 96 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 131 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 218 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 82 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.serde` | 74 | JSON serde helpers shared by the server, daemon, CLI and SDK. | hugrgate |
| `hugrgate.server` | 386 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
| `hugrgate.spec` | 127 | DecisionSpec — the decision contract. Slices 2-3. | hugrgate |
| `hugrgate.threshold` | 213 | Thresholding — per-option, ordinal-cumulative, and numeric-band gates. | hugrgate |
| `hugrgate.timeout` | 139 | Timeouts — per-decision deadline enforcement via threads. Slice 19. | hugrgate |
| `hugrgate.validation` | 131 | Validation layer — the application never receives an invalid value. Slic | hugrgate |

## Findings (forwarded to later slices)

1. `hugrgate/client.py` imports `httpx` at module level, but `httpx` is
   not declared in `pyproject.toml` (only present transitively in the dev
   venv). `hugrgate/cli.py` imports it lazily inside a function.
   → slice 004/008: declare `httpx` in the `server` extra (or make
   `client.py` degrade gracefully when it is absent).
2. `docs/api.md` documents the HTTP surface; the Python API has no
   equivalent inventory page. → slice 003.
3. No machine-readable architecture/dependency map existed before this
   audit. → slice 002/004.

## Verification

Re-run `venv/bin/python tools/audit_repo.py` and diff
`docs/campaign-i/manifest.json`; `tests/test_repo_truth.py` encodes
the key invariants so drift fails the suite.
