# Changelog — HugrGate

## 0.1.0 (2026-10-09) — The Icebox Opens

First implementation release. 50 slices forged via Mythic Engineering.

### Foundation (slices 1–10)
- `DecisionSpec`: categorical, binary, ordinal, numeric, multilabel
- `DecisionResult`: typed value + probability distribution, invariants enforced
- `DecisionPolicy`: application-controlled thresholds
- `Backend` ABC + `BackendRegistry`
- Validation layer, core `decide()`, provenance store, error taxonomy
- `CLEAN_ROOM.md`, `CONTRIBUTING.md`, ADR-001

### Deterministic core (slices 11–20)
- `RuleBackend`: predicates, decision tables, YAML loading, confidence distributions
- `FallbackChain`, abstention, thresholding, health scoring, circuit breakers, timeouts
- Zero-ML milestone: event triage example

### Classical ML + calibration (slices 21–30)
- Feature preprocessing pipeline
- Logistic regression, random forest, gradient boosting backends
- Model manifests + versioned store
- Platt scaling, isotonic regression, temperature scaling (independent implementations)
- Calibration metrics (Brier, log loss, ECE, MCE), versioned profiles
- Calibrated classifier milestone

### Intelligence ladder (slices 31–40)
- `LadderRouter` with confidence gating, latency budgets, privacy gates
- Embedding prototype backend (offline hash embedding)
- NLI backend, constrained-decoding LLM backend
- Capability negotiation, batch inference, decision cache, privacy enforcement

### Service & ecosystem (slices 41–50)
- FastAPI service (`hugrgate/server.py`): `POST /decide` (bare
  `DecisionResult` JSON; abstention → HTTP 200 `{"abstained": true}`),
  `GET /health`, `GET /backends`, `GET /models`; localhost-only default
  `127.0.0.1:8377`; error mapping 400/422/429/502/503
- Built-in deterministic baselines: `uniform` + `keyword` via `build_gate()`
- Daemon mode (`hugrgate/daemon.py`, entry point `hugrgate-server`):
  Unix socket + localhost HTTP, model warm pool, windowed request
  batching with back-pressure (HTTP 429), per-client policies via
  `X-Client-Id`, graceful shutdown with queue draining
- Python client (`hugrgate/client.py`): `HugrGateClient` over HTTP/Unix
  socket with auto-fallback to in-process gate; direct-gate mode
- CLI (`hugrgate/cli.py`, entry point `hugrgate`): `decide`, `backends`,
  `models`, `health`, `serve`, `bench`, `report`
- Benchmark harness (`hugrgate/bench.py`): `run_benchmark()` + `Benchmark`
  — accuracy, Brier, ECE, latency p50/p99, throughput, abstention rate;
  JSON report with dataset fingerprint + platform metadata
- 3 original datasets (`benchmarks/`): intent_500, urgency_500, triage_500
  — 500 items each, seeded builder (`benchmarks/build.py`),
  `CHECKSUMS.sha256`
- Benchmark reports (`hugrgate/bench_report.py`): markdown with metric
  tables, ASCII reliability diagrams, hardware/methodology block
- Drift monitoring (`hugrgate/drift.py`): `DriftMonitor` — PSI histogram
  mode + streaming per-prediction mode, alert/watch thresholds,
  `recalibration_advisory()`
- Docs: quickstart, concepts, backends, calibration, ladder, api,
  release checklist; 5 new worked examples
- Packaging: extras `ml`, `onnx`, `nli`, `llm`, `server`, `bench`

## Contract Engine (2026-10-09) — Gjallarbrú campaign II (slices 026–050)

Versioned, self-describing v2 decision contracts in `hugrgate/contracts/`
(24 modules, 17 kinds), built alongside the untouched v1 `DecisionSpec`.
`ContractError(SpecError)` with per-instance codes.

- 026 Contract schema v2: `DecisionContract`, kind registry, canonical
  SHA-256 hash, dict round-trips
- 027 Version negotiation: rank-sum negotiation, session agreements
- 028 Nested categorical contracts: option trees, dotted leaf paths
- 029 Hierarchical labels: label forests, hierarchical precision/recall
- 030 Structured composite decisions: composites of v2 contracts / v1 specs
- 031 Conditional decision fields: fixpoint activation
- 032 Cross-field constraints: declarative field constraints
- 033 Rich ordinal semantics: anchors, interpolation
- 034 Numeric uncertainty intervals: interval algebra
- 035 Distribution constraints: outcome-space health checks
- 036 Multilabel cardinality constraints
- 037 Cost-sensitive decisions: `CostMatrix`, Bayes-optimal choice
- 038 Utility matrices + cost↔utility duality
- 039 Risk matrices: minimax, regret, CVaR
- 040 Decision deadlines: `TimedContract` (budgets, time windows)
- 041 Context schemas, 042 Input feature contracts
- 043 Output explanation contracts (word-boundary faithfulness)
- 044 Contract inheritance: `derive_contract`, compatibility checks
- 045 Contract composition: merge, product, deadline wrapping
- 046 Contract templates: `${param}` substitution, `TemplateLibrary`
- 047 Contract migration engine: v1 `DecisionSpec` ↔ v2, `(1.0→2.0)`
  registry, `MigrationReport`
- 048 Contract linting: 12+ checks, info/warning/error severities,
  extensible `LINT_CHECKS`, template linting
- 049 Contract fuzzing: seeded generators for 6 kinds, invariant checks
  (round-trip, hash stability, validate soundness); ~15k checks, 0 failures
- 050 Release gate: `HugrGate.decide()`/`decide_batch()` accept v2
  contracts with a v1 equivalent (migrated at the boundary, `contract_id`
  in result metadata); stdlib-only contract dependencies; full suite
  green (876 tests), mypy clean, v1 API untouched
