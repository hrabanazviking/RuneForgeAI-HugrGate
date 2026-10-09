# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T11:52:36.800474+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 68 Python files under `hugrgate/`
- **Total LOC:** 12313
- **pyproject version:** 0.1.0
- **Test files:** test_adaptive_bandit.py, test_adaptive_benchmark.py, test_adaptive_coldstart.py, test_adaptive_competence.py, test_adaptive_contract_competence.py, test_adaptive_cost_quality.py, test_adaptive_counterfactual.py, test_adaptive_delayed.py, test_adaptive_domain_competence.py, test_adaptive_drift.py, test_adaptive_energy_quality.py, test_adaptive_explanations.py, test_adaptive_exploration.py, test_adaptive_feedback.py, test_adaptive_latency_quality.py, test_adaptive_multiobjective.py, test_adaptive_offline.py, test_adaptive_privacy_objective.py, test_adaptive_rollback.py, test_adaptive_router_features.py, test_adaptive_safe_exploration.py, test_adaptive_shadow.py, test_adaptive_telemetry.py, test_adaptive_versioning.py, test_api_inventory.py, test_arch_map.py, test_async_readiness.py, test_backend_registry.py, test_config.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_errors.py, test_foundation.py, test_ladder.py, test_logging.py, test_ml_calibration.py, test_package_boundaries.py, test_policy_invariants.py, test_provenance_integrity.py, test_repo_truth.py, test_resource_lifecycle.py, test_result_invariants.py, test_serialization_contracts.py, test_service.py, test_state_validation.py, test_thread_safety.py, test_typecheck.py

## Module table

| Module | LOC | Docstring | Internal imports |
|---|---|---|---|
| `hugrgate.__init__` | 25 | HugrGate — local-first, model-agnostic probabilistic decision runtime. | hugrgate |
| `hugrgate.abstain` | 111 | Abstention — typed "I don't know" results and review banding. Slice 15. | hugrgate |
| `hugrgate.adaptive.__init__` | 201 | Adaptive routing (Campaign VI) — learn which inference path fits each wo | hugrgate |
| `hugrgate.adaptive.bandit` | 277 | Contextual bandit adapter. Slice 130. | hugrgate |
| `hugrgate.adaptive.benchmark` | 192 | Adaptive routing benchmark. Slice 149. | hugrgate |
| `hugrgate.adaptive.coldstart` | 154 | Cold-start routing. Slice 140. | hugrgate |
| `hugrgate.adaptive.competence` | 215 | Backend competence profiles. Slice 137. | hugrgate |
| `hugrgate.adaptive.contract_competence` | 172 | Per-contract competence. Slice 139. | hugrgate |
| `hugrgate.adaptive.cost_quality` | 139 | Cost-quality objective. Slice 132. | hugrgate |
| `hugrgate.adaptive.counterfactual` | 178 | Counterfactual route evaluation. Slice 144. | hugrgate |
| `hugrgate.adaptive.delayed` | 172 | Delayed-label ingestion. Slice 128. | hugrgate |
| `hugrgate.adaptive.domain_competence` | 169 | Per-domain competence. Slice 138. | hugrgate |
| `hugrgate.adaptive.drift_detect` | 184 | Adaptive-route drift detection. Slice 148. | hugrgate |
| `hugrgate.adaptive.energy_quality` | 127 | Energy-quality objective. Slice 134. | hugrgate |
| `hugrgate.adaptive.explanations` | 189 | Adaptive-route explanations. Slice 147. | hugrgate |
| `hugrgate.adaptive.exploration` | 170 | Exploration controls. Slice 141. | hugrgate |
| `hugrgate.adaptive.feedback` | 165 | Outcome feedback API. Slice 127. | hugrgate |
| `hugrgate.adaptive.latency_quality` | 153 | Latency-quality objective. Slice 133. | hugrgate |
| `hugrgate.adaptive.multiobjective` | 137 | Multi-objective routing. Slice 136. | hugrgate |
| `hugrgate.adaptive.offline` | 149 | Offline policy learning. Slice 131. | hugrgate |
| `hugrgate.adaptive.privacy_objective` | 115 | Privacy-constrained objective. Slice 135. | hugrgate |
| `hugrgate.adaptive.rollback` | 145 | Router rollback. Slice 145. | hugrgate |
| `hugrgate.adaptive.router_features` | 191 | Router feature extraction. Slice 129. | hugrgate |
| `hugrgate.adaptive.safe_exploration` | 127 | Safe exploration. Slice 142. | hugrgate |
| `hugrgate.adaptive.shadow` | 136 | Router shadow mode. Slice 143. | hugrgate |
| `hugrgate.adaptive.telemetry` | 359 | Routing telemetry dataset. Slice 126. | hugrgate |
| `hugrgate.adaptive.versioning` | 174 | Adaptive policy versioning. Slice 146. | hugrgate |
| `hugrgate.backend` | 145 | Backend interface + registry. Slice 6. | hugrgate |
| `hugrgate.backends.boosting` | 69 | Gradient boosting backend. Slice 24. | hugrgate |
| `hugrgate.backends.embedding` | 260 | Embedding backend — prototype classifier. Slice 33. | hugrgate |
| `hugrgate.backends.forest` | 74 | Random forest backend. Slice 23. | hugrgate |
| `hugrgate.backends.llm` | 247 | Local LLM backend — constrained decoding. Slice 35. | hugrgate |
| `hugrgate.backends.logreg` | 303 | Logistic regression backend. Slice 22. | hugrgate |
| `hugrgate.backends.nli` | 153 | NLI backend — statement entailment as a binary decision. Slice 34. | hugrgate |
| `hugrgate.backends.rules` | 380 | Rule backend — predicates, decision tables, confidence distributions. | hugrgate |
| `hugrgate.bench` | 344 | Benchmark harness — datasets → backends → metrics. Slice 45. | hugrgate |
| `hugrgate.bench_report` | 145 | Benchmark report — markdown rendering of benchmark JSON. Slice 47. | — |
| `hugrgate.cache` | 180 | Decision cache — request-hash keyed result memoization. Slice 38. | hugrgate |
| `hugrgate.calibration.__init__` | 47 | Probability calibration package. Slices 26-29. | hugrgate |
| `hugrgate.calibration._base` | 120 | Calibration base classes (private). | hugrgate |
| `hugrgate.calibration.isotonic` | 111 | Isotonic regression via the Pool Adjacent Violators (PAV) algorithm. | hugrgate |
| `hugrgate.calibration.metrics` | 149 | Calibration metrics. Slice 28. | hugrgate |
| `hugrgate.calibration.platt` | 130 | Platt scaling. Slice 26. | hugrgate |
| `hugrgate.calibration.profiles` | 263 | Calibration profiles. Slice 29. | hugrgate |
| `hugrgate.calibration.temperature` | 136 | Temperature scaling. Slice 27. | hugrgate |
| `hugrgate.circuit` | 173 | Circuit breaker — per-backend failure containment. Slice 18. | hugrgate |
| `hugrgate.cli` | 276 | HugrGate command-line interface. Slice 44. | hugrgate |
| `hugrgate.client` | 263 | HugrGate Python SDK — client for the HTTP service. Slice 43. | hugrgate |
| `hugrgate.core` | 158 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 492 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 250 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 142 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
| `hugrgate.fallback` | 170 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 290 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 141 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 317 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.log` | 101 | Structured logging for HugrGate (slice 009). | — |
| `hugrgate.models` | 162 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 96 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 96 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 130 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 217 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 82 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.server` | 368 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
| `hugrgate.spec` | 127 | DecisionSpec — the decision contract. Slices 2-3. | hugrgate |
| `hugrgate.threshold` | 212 | Thresholding — per-option, ordinal-cumulative, and numeric-band gates. | hugrgate |
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
