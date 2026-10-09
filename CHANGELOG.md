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
