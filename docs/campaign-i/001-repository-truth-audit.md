# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T14:25:36.470585+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 93 Python files under `hugrgate/`
- **Total LOC:** 18894
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_async_readiness.py, test_backend_registry.py, test_config.py, test_contracts_026.py, test_contracts_027.py, test_contracts_028.py, test_contracts_029.py, test_contracts_030.py, test_contracts_031.py, test_contracts_032.py, test_contracts_033.py, test_contracts_034.py, test_contracts_035.py, test_contracts_036.py, test_contracts_037.py, test_contracts_038.py, test_contracts_039.py, test_contracts_040.py, test_contracts_041.py, test_contracts_042.py, test_contracts_043.py, test_contracts_044.py, test_contracts_045.py, test_contracts_046.py, test_contracts_047.py, test_contracts_048.py, test_contracts_049.py, test_contracts_050.py, test_coverage_attack.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_errors.py, test_foundation.py, test_import_cycles.py, test_ladder.py, test_logging.py, test_ml_calibration.py, test_package_boundaries.py, test_policy_invariants.py, test_provenance_integrity.py, test_release_gate.py, test_repo_truth.py, test_resource_lifecycle.py, test_result_invariants.py, test_routing_051.py, test_routing_052.py, test_routing_053.py, test_routing_054.py, test_routing_055.py, test_routing_056.py, test_routing_057.py, test_routing_058.py, test_routing_059.py, test_routing_060.py, test_routing_061.py, test_routing_062.py, test_routing_063.py, test_routing_064.py, test_routing_065.py, test_routing_066.py, test_routing_067.py, test_routing_068.py, test_routing_069.py, test_routing_070.py, test_routing_071.py, test_routing_072.py, test_routing_073.py, test_routing_074.py, test_serialization_contracts.py, test_service.py, test_state_validation.py, test_static_analysis.py, test_taxonomy.py, test_thread_safety.py, test_typecheck.py

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
| `hugrgate.contracts.__init__` | 81 | Decision contracts — versioned, self-describing decision specifications. | hugrgate |
| `hugrgate.contracts.composite` | 188 | Structured composite decisions. Gjallarbrú slice 030. | hugrgate |
| `hugrgate.contracts.composition` | 167 | Contract composition — combining contracts. Gjallarbrú slice 045. | hugrgate |
| `hugrgate.contracts.conditional` | 269 | Conditional decision fields. Gjallarbrú slice 031. | hugrgate |
| `hugrgate.contracts.context` | 275 | Context schemas — typed contracts for decision context. | hugrgate |
| `hugrgate.contracts.cost` | 257 | Cost-sensitive decisions — when mistakes have different prices. | hugrgate |
| `hugrgate.contracts.crossfield` | 289 | Cross-field constraints — invariants over whole decisions. | hugrgate |
| `hugrgate.contracts.deadlines` | 209 | Decision deadlines — temporal bounds on decisions. Gjallarbrú slice 040. | hugrgate |
| `hugrgate.contracts.distributions` | 321 | Distribution constraints — what a healthy distribution looks like. | hugrgate |
| `hugrgate.contracts.explanations` | 228 | Output explanation contracts — decisions must show their work. | hugrgate |
| `hugrgate.contracts.features` | 289 | Input feature contracts — what the model may assume. | hugrgate |
| `hugrgate.contracts.fuzz` | 340 | Contract fuzzing — seeded random contracts, invariant checking. | hugrgate |
| `hugrgate.contracts.hierarchy` | 371 | Hierarchical labels — label forests with ancestor semantics. | hugrgate |
| `hugrgate.contracts.inheritance` | 377 | Contract inheritance — derive, specialize, and check compatibility. | hugrgate |
| `hugrgate.contracts.lint` | 346 | Contract linting — static checks with severities. | hugrgate |
| `hugrgate.contracts.migration` | 239 | Contract migration engine — v1 DecisionSpec ↔ v2 contracts. | hugrgate |
| `hugrgate.contracts.multilabel` | 270 | Multilabel cardinality constraints — how many, which, with what. | hugrgate |
| `hugrgate.contracts.negotiation` | 212 | Contract version negotiation. Gjallarbrú slice 027. | hugrgate |
| `hugrgate.contracts.nested` | 196 | Nested categorical contracts — decision trees. Gjallarbrú slice 028. | hugrgate |
| `hugrgate.contracts.ordinal` | 195 | Rich ordinal semantics — ordinals you can measure. Gjallarbrú slice 033. | hugrgate |
| `hugrgate.contracts.risk` | 242 | Risk matrices — deciding under risk aversion. Gjallarbrú slice 039. | hugrgate |
| `hugrgate.contracts.schema` | 242 | Decision contract schema v2. Gjallarbrú slice 026. | hugrgate |
| `hugrgate.contracts.templates` | 331 | Contract templates — reusable parameterized contracts. | hugrgate |
| `hugrgate.contracts.uncertainty` | 233 | Numeric uncertainty intervals. Gjallarbrú slice 034. | hugrgate |
| `hugrgate.contracts.utility` | 274 | Utility matrices — decisions as gains, not just losses. | hugrgate |
| `hugrgate.core` | 201 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 494 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 152 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
| `hugrgate.fallback` | 171 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 291 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 140 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 343 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.log` | 101 | Structured logging for HugrGate (slice 009). | — |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 96 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 131 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 218 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 82 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.routing.__init__` | 211 | Ladder II — intelligence routing subsystem (Campaign III). | hugrgate |
| `hugrgate.routing.architecture` | 403 | Router architecture v2 — plan/execute separation. Slice 051. | hugrgate |
| `hugrgate.routing.availability` | 140 | Availability-aware routing. Slice 062. | hugrgate |
| `hugrgate.routing.capability` | 148 | Capability scoring. Slice 054. | hugrgate |
| `hugrgate.routing.confidence` | 141 | Confidence-aware routing. Slice 055. | hugrgate |
| `hugrgate.routing.cost` | 129 | Cost-aware routing. Slice 057. | hugrgate |
| `hugrgate.routing.dag` | 299 | Conditional routing DAGs. Slice 068. | hugrgate |
| `hugrgate.routing.dsl` | 319 | Route policy DSL. Slice 072. | hugrgate |
| `hugrgate.routing.early_exit` | 184 | Early-exit routing. Slice 066. | hugrgate |
| `hugrgate.routing.energy` | 171 | Energy-aware routing. Slice 058. | hugrgate |
| `hugrgate.routing.explain` | 125 | Route explanation. Slice 069. | hugrgate |
| `hugrgate.routing.fallback` | 239 | Fallback graph routing. Slice 067. | hugrgate |
| `hugrgate.routing.fuzz` | 263 | Routing fuzz tests. Slice 073. | hugrgate |
| `hugrgate.routing.hardware` | 135 | Hardware-aware routing. Slice 061. | hugrgate |
| `hugrgate.routing.hedged` | 212 | Hedged inference. Slice 065. | hugrgate |
| `hugrgate.routing.latency` | 121 | Latency-aware routing. Slice 056. | hugrgate |
| `hugrgate.routing.memory` | 105 | Memory-aware routing. Slice 059. | hugrgate |
| `hugrgate.routing.parallel` | 156 | Parallel speculative rungs. Slice 064. | hugrgate |
| `hugrgate.routing.privacy` | 161 | Privacy-aware routing v2. Slice 060. | hugrgate |
| `hugrgate.routing.qos` | 96 | Quality-of-service classes. Slice 063. | — |
| `hugrgate.routing.replay` | 206 | Route replay. Slice 070. | hugrgate |
| `hugrgate.routing.rungs` | 146 | Dynamic rung construction. Slice 052. | hugrgate |
| `hugrgate.routing.simulate` | 152 | Route simulation. Slice 071. | hugrgate |
| `hugrgate.routing.synthesis` | 112 | Per-request ladder synthesis. Slice 053. | hugrgate |
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
