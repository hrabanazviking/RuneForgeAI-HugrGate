# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T11:44:24.583961+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 62 Python files under `hugrgate/`
- **Total LOC:** 12119
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_contracts_026.py, test_contracts_027.py, test_contracts_028.py, test_contracts_029.py, test_contracts_030.py, test_contracts_031.py, test_contracts_032.py, test_contracts_033.py, test_contracts_034.py, test_contracts_035.py, test_contracts_036.py, test_contracts_037.py, test_contracts_038.py, test_contracts_039.py, test_contracts_040.py, test_contracts_041.py, test_contracts_042.py, test_contracts_043.py, test_contracts_044.py, test_dead_code.py, test_dependency_rules.py, test_deterministic.py, test_foundation.py, test_ladder.py, test_ml_calibration.py, test_repo_truth.py, test_service.py, test_typecheck.py

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
| `hugrgate.contracts.__init__` | 63 | Decision contracts — versioned, self-describing decision specifications. | hugrgate |
| `hugrgate.contracts.composite` | 187 | Structured composite decisions. Gjallarbrú slice 030. | hugrgate |
| `hugrgate.contracts.conditional` | 268 | Conditional decision fields. Gjallarbrú slice 031. | hugrgate |
| `hugrgate.contracts.context` | 274 | Context schemas — typed contracts for decision context. | hugrgate |
| `hugrgate.contracts.cost` | 256 | Cost-sensitive decisions — when mistakes have different prices. | hugrgate |
| `hugrgate.contracts.crossfield` | 289 | Cross-field constraints — invariants over whole decisions. | hugrgate |
| `hugrgate.contracts.deadlines` | 208 | Decision deadlines — temporal bounds on decisions. Gjallarbrú slice 040. | hugrgate |
| `hugrgate.contracts.distributions` | 320 | Distribution constraints — what a healthy distribution looks like. | hugrgate |
| `hugrgate.contracts.explanations` | 227 | Output explanation contracts — decisions must show their work. | hugrgate |
| `hugrgate.contracts.features` | 288 | Input feature contracts — what the model may assume. | hugrgate |
| `hugrgate.contracts.hierarchy` | 370 | Hierarchical labels — label forests with ancestor semantics. | hugrgate |
| `hugrgate.contracts.inheritance` | 339 | Contract inheritance — derive, specialize, and check compatibility. | hugrgate |
| `hugrgate.contracts.multilabel` | 269 | Multilabel cardinality constraints — how many, which, with what. | hugrgate |
| `hugrgate.contracts.negotiation` | 212 | Contract version negotiation. Gjallarbrú slice 027. | hugrgate |
| `hugrgate.contracts.nested` | 195 | Nested categorical contracts — decision trees. Gjallarbrú slice 028. | hugrgate |
| `hugrgate.contracts.ordinal` | 193 | Rich ordinal semantics — ordinals you can measure. Gjallarbrú slice 033. | hugrgate |
| `hugrgate.contracts.risk` | 241 | Risk matrices — deciding under risk aversion. Gjallarbrú slice 039. | hugrgate |
| `hugrgate.contracts.schema` | 243 | Decision contract schema v2. Gjallarbrú slice 026. | hugrgate |
| `hugrgate.contracts.uncertainty` | 232 | Numeric uncertainty intervals. Gjallarbrú slice 034. | hugrgate |
| `hugrgate.contracts.utility` | 273 | Utility matrices — decisions as gains, not just losses. | hugrgate |
| `hugrgate.core` | 111 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 394 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 83 | Error taxonomy for HugrGate. Slice 10. | — |
| `hugrgate.fallback` | 165 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 290 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 141 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 289 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 59 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 123 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 84 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 64 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
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
