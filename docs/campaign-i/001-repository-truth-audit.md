# Slice 001 — Repository truth audit

**Generated:** 2026-10-09T10:45:26.783815+00:00 (deterministic re-runnable via `tools/audit_repo.py`)

## Inventory

- **Modules:** 42 Python files under `hugrgate/`
- **Total LOC:** 6666
- **pyproject version:** 0.1.0
- **Test files:** test_arch_map.py, test_deterministic.py, test_foundation.py, test_ladder.py, test_ml_calibration.py, test_repo_truth.py, test_service.py

## Module table

| Module | LOC | Docstring | Internal imports |
|---|---|---|---|
| `hugrgate.__init__` | 25 | HugrGate — local-first, model-agnostic probabilistic decision runtime. | hugrgate |
| `hugrgate.abstain` | 105 | Abstention — typed "I don't know" results and review banding. Slice 15. | hugrgate |
| `hugrgate.backend` | 79 | Backend interface + registry. Slice 6. | hugrgate |
| `hugrgate.backends.boosting` | 51 | Gradient boosting backend. Slice 24. | hugrgate |
| `hugrgate.backends.embedding` | 236 | Embedding backend — prototype classifier. Slice 33. | hugrgate |
| `hugrgate.backends.forest` | 52 | Random forest backend. Slice 23. | hugrgate |
| `hugrgate.backends.llm` | 239 | Local LLM backend — constrained decoding. Slice 35. | hugrgate |
| `hugrgate.backends.logreg` | 281 | Logistic regression backend. Slice 22. | hugrgate |
| `hugrgate.backends.nli` | 144 | NLI backend — statement entailment as a binary decision. Slice 34. | hugrgate |
| `hugrgate.backends.rules` | 373 | Rule backend — predicates, decision tables, confidence distributions. | hugrgate |
| `hugrgate.bench` | 321 | Benchmark harness — datasets → backends → metrics. Slice 45. | hugrgate |
| `hugrgate.bench_report` | 139 | Benchmark report — markdown rendering of benchmark JSON. Slice 47. | — |
| `hugrgate.cache` | 156 | Decision cache — request-hash keyed result memoization. Slice 38. | hugrgate |
| `hugrgate.calibration.__init__` | 47 | Probability calibration package. Slices 26-29. | hugrgate |
| `hugrgate.calibration._base` | 102 | Calibration base classes (private). | hugrgate |
| `hugrgate.calibration.isotonic` | 94 | Isotonic regression via the Pool Adjacent Violators (PAV) algorithm. | hugrgate |
| `hugrgate.calibration.metrics` | 123 | Calibration metrics. Slice 28. | — |
| `hugrgate.calibration.platt` | 112 | Platt scaling. Slice 26. | hugrgate |
| `hugrgate.calibration.profiles` | 244 | Calibration profiles. Slice 29. | hugrgate |
| `hugrgate.calibration.temperature` | 116 | Temperature scaling. Slice 27. | hugrgate |
| `hugrgate.circuit` | 156 | Circuit breaker — per-backend failure containment. Slice 18. | — |
| `hugrgate.cli` | 258 | HugrGate command-line interface. Slice 44. | hugrgate |
| `hugrgate.client` | 232 | HugrGate Python SDK — client for the HTTP service. Slice 43. | hugrgate |
| `hugrgate.core` | 107 | HugrGate core runtime — decide(). Slice 8. | hugrgate |
| `hugrgate.daemon` | 378 | HugrGate service daemon — long-running process mode. Slice 42. | hugrgate |
| `hugrgate.drift` | 241 | Calibration drift detection — PSI over prediction distributions. Slice 4 | — |
| `hugrgate.errors` | 60 | Error taxonomy for HugrGate. Slice 10. | — |
| `hugrgate.fallback` | 159 | Fallback engine — ordered failover across backends. Slice 14. | hugrgate |
| `hugrgate.features` | 268 | Feature preprocessing contract. Slice 21. | hugrgate |
| `hugrgate.health` | 136 | Backend health scoring — latency, errors, quarantine. Slice 17. | — |
| `hugrgate.ladder` | 274 | Intelligence ladder — ordered backend cascade. Slices 31-32. | hugrgate |
| `hugrgate.models` | 156 | Model manifests and a disk-backed versioned model store. Slice 25. | hugrgate |
| `hugrgate.negotiate` | 90 | Backend capability negotiation. Slice 36. | hugrgate |
| `hugrgate.policy` | 55 | DecisionPolicy — application-controlled thresholds. Slice 5. | hugrgate |
| `hugrgate.privacy` | 117 | Privacy enforcement — system-level guardrails. Slice 40. | hugrgate |
| `hugrgate.provenance` | 79 | Decision provenance — why did the program take this branch? Slice 9. | hugrgate |
| `hugrgate.result` | 60 | DecisionResult — typed value + probability distribution. Slice 4. | hugrgate |
| `hugrgate.server` | 354 | HugrGate local HTTP API — FastAPI service. Slice 41. | hugrgate |
| `hugrgate.spec` | 104 | DecisionSpec — the decision contract. Slices 2-3. | hugrgate |
| `hugrgate.threshold` | 159 | Thresholding — per-option, ordinal-cumulative, and numeric-band gates. | hugrgate |
| `hugrgate.timeout` | 131 | Timeouts — per-decision deadline enforcement via threads. Slice 19. | hugrgate |
| `hugrgate.validation` | 53 | Validation layer — the application never receives an invalid value. Slic | hugrgate |

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
