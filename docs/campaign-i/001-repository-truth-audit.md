# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T13:21:49.265355+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 63 Python files under `hugrgate/`
- **Total LOC:** 13300
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_async_readiness.py, test_backend_registry.py, test_config.py, test_coverage_attack.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_edge_affinity.py, test_edge_bench.py, test_edge_bootstrap.py, test_edge_cachetune.py, test_edge_chaos.py, test_edge_gate.py, test_edge_memory.py, test_edge_npu.py, test_edge_platform.py, test_edge_power.py, test_edge_quant.py, test_edge_recovery.py, test_edge_residency.py, test_edge_storage.py, test_edge_telemetry.py, test_edge_thermal.py, test_edge_watchdog.py, test_errors.py, test_foundation.py, test_import_cycles.py, test_ladder.py, test_logging.py, test_ml_calibration.py, test_package_boundaries.py, test_policy_invariants.py, test_provenance_integrity.py, test_release_gate.py, test_repo_truth.py, test_resource_lifecycle.py, test_result_invariants.py, test_serialization_contracts.py, test_service.py, test_state_validation.py, test_static_analysis.py, test_taxonomy.py, test_thread_safety.py, test_typecheck.py

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
| `hugrgate.core` | 159 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 494 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.edge.__init__` | 269 | Edge Intelligence runtime — Campaign VIII (slices 176-200). | hugrgate |
| `hugrgate.edge.affinity` | 232 | CPU affinity controls for edge inference. Slice 179. | hugrgate |
| `hugrgate.edge.bench` | 458 | Edge benchmark harness and platform suites. Slices 196-198. | hugrgate |
| `hugrgate.edge.bootstrap` | 294 | Offline-first bootstrap for edge deployment. Slice 192. | hugrgate |
| `hugrgate.edge.cachetune` | 157 | Edge-tuned decision cache sizing. Slice 190. | hugrgate |
| `hugrgate.edge.chaos` | 259 | Edge failure testing — deterministic fault injection. Slice 199. | hugrgate |
| `hugrgate.edge.gate` | 258 | Edge Intelligence release gate. Slice 200. | hugrgate |
| `hugrgate.edge.memory` | 210 | Low-RAM operating modes for edge deployment. Slice 178. | hugrgate |
| `hugrgate.edge.npu` | 507 | NPU capability abstraction and vendor adapter boundaries. | hugrgate |
| `hugrgate.edge.platform` | 472 | Edge platform detection, ARM64 audit, and Raspberry Pi baselines. | — |
| `hugrgate.edge.power` | 152 | Power-budget routing for edge deployment. Slice 181. | hugrgate |
| `hugrgate.edge.quant` | 577 | Quantized-model profiles and simulated quantization paths. Slices 182-18 | hugrgate |
| `hugrgate.edge.recovery` | 191 | Intermittent-power recovery via checkpoint journal. Slice 193. | hugrgate |
| `hugrgate.edge.residency` | 199 | Edge model residency management. Slice 189. | hugrgate |
| `hugrgate.edge.routing` | 146 | Edge-aware backend routing. Slices 180-181. | hugrgate |
| `hugrgate.edge.storage` | 283 | Flash-wear-aware storage for edge devices. Slice 191. | hugrgate |
| `hugrgate.edge.telemetry` | 174 | Edge telemetry lite — bounded, privacy-safe metrics. Slice 195. | hugrgate |
| `hugrgate.edge.thermal` | 182 | Thermal sensing and thermal-aware derating. Slice 180. | — |
| `hugrgate.edge.watchdog` | 164 | Edge watchdog — heartbeat supervision for the edge runtime. Slice 194. | hugrgate |
| `hugrgate.errors` | 253 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
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
| `hugrgate.server` | 370 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
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
