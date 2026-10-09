# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T11:25:38.005202+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 66 Python files under `hugrgate/`
- **Total LOC:** 11436
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_dead_code.py, test_dependency_rules.py, test_deterministic.py, test_foundation.py, test_ladder.py, test_ml_calibration.py, test_repo_truth.py, test_routing_051.py, test_routing_052.py, test_routing_053.py, test_routing_054.py, test_routing_055.py, test_routing_056.py, test_routing_057.py, test_routing_058.py, test_routing_059.py, test_routing_060.py, test_routing_061.py, test_routing_062.py, test_routing_063.py, test_routing_064.py, test_routing_065.py, test_routing_066.py, test_routing_067.py, test_routing_068.py, test_routing_069.py, test_routing_070.py, test_routing_071.py, test_routing_072.py, test_routing_073.py, test_routing_074.py, test_service.py, test_typecheck.py

## Module table

| Module | LOC | Docstring | Internal imports |
|---|---|---|---|
| `hugrgate.__init__` | 25 | HugrGate — local-first, model-agnostic probabilistic decision runtime. | hugrgate |
| `hugrgate.abstain` | 111 | Abstention — typed "I don't know" results and review banding. Slice 15. | hugrgate |
| `hugrgate.backend` | 84 | Backend interface + registry. Slice 6. | hugrgate |
| `hugrgate.backends.boosting` | 69 | Gradient boosting backend. Slice 24. | hugrgate |
| `hugrgate.backends.embedding` | 260 | Embedding backend — prototype classifier. Slice 33. | hugrgate |
| `hugrgate.backends.forest` | 74 | Random forest backend. Slice 23. | hugrgate |
| `hugrgate.backends.llm` | 247 | Local LLM backend — constrained decoding. Slice 35. | hugrgate |
| `hugrgate.backends.logreg` | 303 | Logistic regression backend. Slice 22. | hugrgate |
| `hugrgate.backends.nli` | 153 | NLI backend — statement entailment as a binary decision. Slice 34. | hugrgate |
| `hugrgate.backends.rules` | 380 | Rule backend — predicates, decision tables, confidence distributions. | hugrgate |
| `hugrgate.bench` | 346 | Benchmark harness — datasets → backends → metrics. Slice 45. | hugrgate |
| `hugrgate.bench_report` | 145 | Benchmark report — markdown rendering of benchmark JSON. Slice 47. | — |
| `hugrgate.cache` | 161 | Decision cache — request-hash keyed result memoization. Slice 38. | hugrgate |
| `hugrgate.calibration.__init__` | 47 | Probability calibration package. Slices 26-29. | hugrgate |
| `hugrgate.calibration._base` | 120 | Calibration base classes (private). | hugrgate |
| `hugrgate.calibration.isotonic` | 111 | Isotonic regression via the Pool Adjacent Violators (PAV) algorithm. | hugrgate |
| `hugrgate.calibration.metrics` | 149 | Calibration metrics. Slice 28. | hugrgate |
| `hugrgate.calibration.platt` | 130 | Platt scaling. Slice 26. | hugrgate |
| `hugrgate.calibration.profiles` | 263 | Calibration profiles. Slice 29. | hugrgate |
| `hugrgate.calibration.temperature` | 136 | Temperature scaling. Slice 27. | hugrgate |
| `hugrgate.circuit` | 164 | Circuit breaker — per-backend failure containment. Slice 18. | — |
| `hugrgate.cli` | 275 | HugrGate command-line interface. Slice 44. | hugrgate |
| `hugrgate.client` | 261 | HugrGate Python SDK — client for the HTTP service. Slice 43. | hugrgate |
| `hugrgate.core` | 111 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 394 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 72 | Error taxonomy for HugrGate. Slice 10. | — |
| `hugrgate.fallback` | 165 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 290 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 141 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 305 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 59 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 123 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 84 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 64 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.routing.__init__` | 207 | Ladder II — intelligence routing subsystem (Campaign III). | hugrgate |
| `hugrgate.routing.architecture` | 399 | Router architecture v2 — plan/execute separation. Slice 051. | hugrgate |
| `hugrgate.routing.availability` | 137 | Availability-aware routing. Slice 062. | hugrgate |
| `hugrgate.routing.capability` | 148 | Capability scoring. Slice 054. | hugrgate |
| `hugrgate.routing.confidence` | 138 | Confidence-aware routing. Slice 055. | hugrgate |
| `hugrgate.routing.cost` | 126 | Cost-aware routing. Slice 057. | hugrgate |
| `hugrgate.routing.dag` | 289 | Conditional routing DAGs. Slice 068. | hugrgate |
| `hugrgate.routing.dsl` | 318 | Route policy DSL. Slice 072. | hugrgate |
| `hugrgate.routing.early_exit` | 175 | Early-exit routing. Slice 066. | hugrgate |
| `hugrgate.routing.energy` | 168 | Energy-aware routing. Slice 058. | hugrgate |
| `hugrgate.routing.explain` | 120 | Route explanation. Slice 069. | hugrgate |
| `hugrgate.routing.fallback` | 230 | Fallback graph routing. Slice 067. | hugrgate |
| `hugrgate.routing.fuzz` | 254 | Routing fuzz tests. Slice 073. | hugrgate |
| `hugrgate.routing.hardware` | 132 | Hardware-aware routing. Slice 061. | hugrgate |
| `hugrgate.routing.hedged` | 193 | Hedged inference. Slice 065. | hugrgate |
| `hugrgate.routing.latency` | 119 | Latency-aware routing. Slice 056. | hugrgate |
| `hugrgate.routing.memory` | 103 | Memory-aware routing. Slice 059. | hugrgate |
| `hugrgate.routing.parallel` | 149 | Parallel speculative rungs. Slice 064. | hugrgate |
| `hugrgate.routing.privacy` | 158 | Privacy-aware routing v2. Slice 060. | hugrgate |
| `hugrgate.routing.qos` | 97 | Quality-of-service classes. Slice 063. | — |
| `hugrgate.routing.replay` | 200 | Route replay. Slice 070. | hugrgate |
| `hugrgate.routing.rungs` | 138 | Dynamic rung construction. Slice 052. | hugrgate |
| `hugrgate.routing.simulate` | 152 | Route simulation. Slice 071. | hugrgate |
| `hugrgate.routing.synthesis` | 109 | Per-request ladder synthesis. Slice 053. | hugrgate |
| `hugrgate.server` | 368 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
| `hugrgate.spec` | 114 | DecisionSpec — the decision contract. Slices 2-3. | hugrgate |
| `hugrgate.threshold` | 167 | Thresholding — per-option, ordinal-cumulative, and numeric-band gates. | hugrgate |
| `hugrgate.timeout` | 138 | Timeouts — per-decision deadline enforcement via threads. Slice 19. | hugrgate |
| `hugrgate.validation` | 60 | Validation layer — the application never receives an invalid value. Slic | hugrgate |

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
