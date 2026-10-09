# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T12:24:19.444258+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 66 Python files under `hugrgate/`
- **Total LOC:** 12581
- **pyproject version:** 0.1.0
- **Test files:** test_api_inventory.py, test_arch_map.py, test_async_readiness.py, test_backend_registry.py, test_config.py, test_coverage_attack.py, test_dead_code.py, test_dependency_rules.py, test_determinism_contract.py, test_deterministic.py, test_ensemble_101_api.py, test_ensemble_102_hard_voting.py, test_ensemble_103_soft_voting.py, test_ensemble_104_weighted_voting.py, test_ensemble_105_confidence_voting.py, test_ensemble_106_bma.py, test_ensemble_107_stacking.py, test_ensemble_108_blending.py, test_ensemble_109_moe.py, test_ensemble_110_diversity.py, test_ensemble_111_disagreement.py, test_ensemble_112_escalation.py, test_ensemble_113_consensus.py, test_ensemble_114_minority.py, test_ensemble_115_correlation.py, test_ensemble_116_reliability.py, test_ensemble_117_membership.py, test_ensemble_118_calibration.py, test_ensemble_119_provenance.py, test_ensemble_120_explanations.py, test_ensemble_121_caching.py, test_ensemble_122_batch.py, test_ensemble_123_adversarial.py, test_ensemble_124_benchmarks.py, test_ensemble_125_release.py, test_errors.py, test_foundation.py, test_import_cycles.py, test_ladder.py, test_logging.py, test_ml_calibration.py, test_package_boundaries.py, test_policy_invariants.py, test_provenance_integrity.py, test_release_gate.py, test_repo_truth.py, test_resource_lifecycle.py, test_result_invariants.py, test_serialization_contracts.py, test_service.py, test_state_validation.py, test_static_analysis.py, test_taxonomy.py, test_thread_safety.py, test_typecheck.py

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
| `hugrgate.ensemble.__init__` | 231 | Ensemble intelligence — one decision from many backends. Slices 101-125. | hugrgate |
| `hugrgate.ensemble.adversarial` | 229 | Ensemble adversarial tests — kick the council and see. Slice 123. | hugrgate |
| `hugrgate.ensemble.api` | 268 | Ensemble API — one decision from many backends. Slice 101. | hugrgate |
| `hugrgate.ensemble.averaging` | 193 | Bayesian model averaging adapter. Slice 106. | hugrgate |
| `hugrgate.ensemble.base` | 329 | Ensemble foundations — shared vote plumbing. Slice 101. | hugrgate |
| `hugrgate.ensemble.batch` | 162 | Ensemble batch mode — one council session, many rulings. Slice 122. | hugrgate |
| `hugrgate.ensemble.benchmarks` | 204 | Ensemble benchmarks — measured, not promised. Slice 125 needs these | hugrgate |
| `hugrgate.ensemble.blending` | 224 | Blending engine — convex member weights from holdout data. Slice 108. | hugrgate |
| `hugrgate.ensemble.cache` | 165 | Ensemble cache — don't re-ask the council. Slice 121. | hugrgate |
| `hugrgate.ensemble.calibration` | 214 | Ensemble calibration — honest probabilities out. Slice 118. | hugrgate |
| `hugrgate.ensemble.consensus` | 136 | Consensus thresholds — supermajority gates. Slice 113. | hugrgate |
| `hugrgate.ensemble.correlation` | 139 | Correlated-error detection — finding members that fail as one. Slice 115 | hugrgate |
| `hugrgate.ensemble.disagreement` | 295 | Disagreement detection, escalation, and minority reports. Slices 111-112 | hugrgate |
| `hugrgate.ensemble.diversity` | 182 | Diversity metrics — measuring *useful* disagreement. Slice 110. | hugrgate |
| `hugrgate.ensemble.explanations` | 167 | Ensemble explanations — the council's reasoning in plain words. Slice 12 | hugrgate |
| `hugrgate.ensemble.membership` | 182 | Dynamic ensemble membership — earn your seat. Slice 117. | hugrgate |
| `hugrgate.ensemble.moe` | 249 | Mixture-of-experts router — route by input region. Slice 109. | hugrgate |
| `hugrgate.ensemble.provenance` | 88 | Ensemble provenance — every council ruling on the record. Slice 119. | hugrgate |
| `hugrgate.ensemble.release` | 262 | Ensemble release gate — the council earns its deployment. Slice 125. | hugrgate |
| `hugrgate.ensemble.reliability` | 139 | Backend reliability weighting — trust, but verify. Slice 116. | hugrgate |
| `hugrgate.ensemble.stacking` | 260 | Stacking engine — a meta-learner over member predictions. Slice 107. | hugrgate |
| `hugrgate.ensemble.voting` | 259 | Voting combiners — many ballots, one decision. Slices 101-105. | hugrgate |
| `hugrgate.errors` | 141 | Error taxonomy for HugrGate. Slice 10; hardened in slice 007. | — |
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
