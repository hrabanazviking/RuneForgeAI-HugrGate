# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T11:59:15.984846+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 67 Python files under `hugrgate/`
- **Total LOC:** 11649
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_backend_registry.py, test_calib_adversarial.py, test_calib_aleatoric.py, test_calib_autoselect.py, test_calib_bayes.py, test_calib_bench.py, test_calib_conformal.py, test_calib_conformal_reg.py, test_calib_coverage.py, test_calib_decomposition.py, test_calib_drift.py, test_calib_ensemble.py, test_calib_epistemic.py, test_calib_group.py, test_calib_imbalance.py, test_calib_online.py, test_calib_perclass.py, test_calib_pipeline.py, test_calib_registry.py, test_calib_risk_coverage.py, test_calib_selective.py, test_calib_sets.py, test_calib_shift.py, test_calib_viz.py, test_calib_window.py, test_config.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_errors.py, test_foundation.py, test_ladder.py, test_logging.py, test_ml_calibration.py, test_policy_invariants.py, test_provenance_integrity.py, test_repo_truth.py, test_result_invariants.py, test_service.py, test_state_validation.py, test_typecheck.py

## Module table

| Module | LOC | Docstring | Internal imports |
|---|---|---|---|
| `hugrgate.__init__` | 25 | HugrGate — local-first, model-agnostic probabilistic decision runtime. | hugrgate |
| `hugrgate.abstain` | 111 | Abstention — typed "I don't know" results and review banding. Slice 15. | hugrgate |
| `hugrgate.backend` | 127 | Backend interface + registry. Slice 6. | hugrgate |
| `hugrgate.backends.boosting` | 69 | Gradient boosting backend. Slice 24. | hugrgate |
| `hugrgate.backends.embedding` | 260 | Embedding backend — prototype classifier. Slice 33. | hugrgate |
| `hugrgate.backends.forest` | 74 | Random forest backend. Slice 23. | hugrgate |
| `hugrgate.backends.llm` | 247 | Local LLM backend — constrained decoding. Slice 35. | hugrgate |
| `hugrgate.backends.logreg` | 303 | Logistic regression backend. Slice 22. | hugrgate |
| `hugrgate.backends.nli` | 153 | NLI backend — statement entailment as a binary decision. Slice 34. | hugrgate |
| `hugrgate.backends.rules` | 380 | Rule backend — predicates, decision tables, confidence distributions. | hugrgate |
| `hugrgate.bench` | 346 | Benchmark harness — datasets → backends → metrics. Slice 45. | hugrgate |
| `hugrgate.bench_report` | 145 | Benchmark report — markdown rendering of benchmark JSON. Slice 47. | — |
| `hugrgate.cache` | 167 | Decision cache — request-hash keyed result memoization. Slice 38. | hugrgate |
| `hugrgate.calibration.__init__` | 89 | Probability calibration package. Slices 26-29. | hugrgate |
| `hugrgate.calibration._base` | 120 | Calibration base classes (private). | hugrgate |
| `hugrgate.calibration.adversarial` | 169 | Calibration adversarial tests. Slice 098. | hugrgate |
| `hugrgate.calibration.aleatoric` | 132 | Aleatoric uncertainty adapters. Slice 096. | hugrgate |
| `hugrgate.calibration.autoselect` | 153 | Calibration auto-selection. Slice 092. | hugrgate |
| `hugrgate.calibration.bayes` | 180 | Bayesian calibration research adapter. Slice 081. | hugrgate |
| `hugrgate.calibration.bench` | 156 | Calibration benchmark suite. Slice 099. | hugrgate |
| `hugrgate.calibration.conformal` | 156 | Split-conformal classification. Slice 082. | hugrgate |
| `hugrgate.calibration.conformal_regression` | 149 | Split-conformal regression. Slice 083. | hugrgate |
| `hugrgate.calibration.coverage` | 167 | Coverage guarantees tooling. Slice 085. | hugrgate |
| `hugrgate.calibration.decomposition` | 112 | Uncertainty decomposition. Slice 094. | hugrgate |
| `hugrgate.calibration.drift` | 181 | Calibration under drift. Slice 088. | hugrgate |
| `hugrgate.calibration.ensemble` | 133 | Calibration ensemble. Slice 093. | hugrgate |
| `hugrgate.calibration.epistemic` | 137 | Epistemic uncertainty adapters. Slice 095. | hugrgate |
| `hugrgate.calibration.group` | 156 | Group calibration. Slice 078. | hugrgate |
| `hugrgate.calibration.imbalance` | 177 | Calibration under class imbalance. Slice 089. | hugrgate |
| `hugrgate.calibration.isotonic` | 111 | Isotonic regression via the Pool Adjacent Violators (PAV) algorithm. | hugrgate |
| `hugrgate.calibration.metrics` | 149 | Calibration metrics. Slice 28. | hugrgate |
| `hugrgate.calibration.online` | 178 | Online (incremental) calibration. Slice 079. | hugrgate |
| `hugrgate.calibration.perclass` | 232 | Per-class calibration. Slice 077. | hugrgate |
| `hugrgate.calibration.pipeline` | 244 | Calibration pipeline (architecture v2). Slice 076. | hugrgate |
| `hugrgate.calibration.platt` | 130 | Platt scaling. Slice 26. | hugrgate |
| `hugrgate.calibration.profiles` | 276 | Calibration profiles. Slice 29. | hugrgate |
| `hugrgate.calibration.registry` | 172 | Calibration registry (rich catalog). Slice 091. | hugrgate |
| `hugrgate.calibration.risk_coverage` | 147 | Risk-coverage curves. Slice 087. | hugrgate |
| `hugrgate.calibration.selective` | 125 | Selective prediction curves. Slice 086. | hugrgate |
| `hugrgate.calibration.sets` | 187 | Prediction sets. Slice 084. | hugrgate |
| `hugrgate.calibration.shift` | 165 | Calibration under distribution shift. Slice 090. | hugrgate |
| `hugrgate.calibration.temperature` | 136 | Temperature scaling. Slice 27. | hugrgate |
| `hugrgate.calibration.viz` | 170 | Calibration visualization data. Slice 097. | hugrgate |
| `hugrgate.calibration.window` | 158 | Sliding-window calibration. Slice 080. | hugrgate |
| `hugrgate.circuit` | 173 | Circuit breaker — per-backend failure containment. Slice 18. | hugrgate |
| `hugrgate.cli` | 275 | HugrGate command-line interface. Slice 44. | hugrgate |
| `hugrgate.client` | 277 | HugrGate Python SDK — client for the HTTP service. Slice 43. | hugrgate |
| `hugrgate.core` | 120 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 445 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 142 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
| `hugrgate.fallback` | 170 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 290 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 141 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 294 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.log` | 101 | Structured logging for HugrGate (slice 009). | — |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 77 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 130 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 129 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 82 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.server` | 368 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
| `hugrgate.spec` | 127 | DecisionSpec — the decision contract. Slices 2-3. | hugrgate |
| `hugrgate.threshold` | 178 | Thresholding — per-option, ordinal-cumulative, and numeric-band gates. | hugrgate |
| `hugrgate.timeout` | 138 | Timeouts — per-decision deadline enforcement via threads. Slice 19. | hugrgate |
| `hugrgate.validation` | 130 | Validation layer — the application never receives an invalid value. Slic | hugrgate |

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
