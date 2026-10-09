# Changelog — HugrGate

## Unreleased — Gjallarbrú Campaign VII: Local Model Fabric

New `hugrgate/runtimes/` layer (slices 151–175): a v2 local-runtime
contract (`LocalRuntime`, `RuntimeRegistry`, `ModelRef`) with eight
engine adapters (llama.cpp, Ollama, ONNX Runtime, Transformers,
vLLM, MLX, OpenVINO, TensorRT), GGUF discovery, a model metadata
scanner, capability probing, structured/grammar/JSON-schema
constrained decoding, curated NLI/embedding/classifier model packs,
and serving operations — warmup manager, ref-counted residency
manager, LRU/TTL/memory-pressure eviction, health probes, a
contract conformance suite, and a measured benchmark matrix
(`benchmarks/localrt-matrix.json`).

### Added
- `GGUFError` to the error taxonomy (`hugrgate.errors`, code
  `gguf_error`, recoverable; re-exported from `hugrgate` and
  `hugrgate.runtimes.gguf`)
- `local-runtimes` layer in the architecture map (below backends,
  above contracts — pinned by `test_dependency_rules.py`)
- `onnx` distribution added to the `hugrgate[onnx]` extra (the
  metadata scanner's deep ONNX scan imports it)

### Fixed
- `LlamaCppRuntime.warmup()` raised with no model loaded; now a
  no-op like every sibling adapter (contract conformance)
- `StructuredRuntime.generate_structured` and
  `JsonSchemaConstrainedRuntime` built `GenerationOptions` with
  both `grammar` and `json_schema` (mutually exclusive); now a
  `SpecError` conflict, consistent policy
- `ResidencyManager.release()` unloaded at refcount zero, leaving
  nothing for eviction; models now stay warm until `evict()`
- `probe.probe_runtime` renamed `probe_capabilities` (name collided
  with `health_probes.probe_runtime`)
- `gen_api_inventory.py` emitted nondeterministic constant reprs
  (memory addresses, set order); now stable

## Unreleased — Gjallarbrú Campaign I: Iron Foundation

Audit-and-harden campaign over the existing codebase (slices
gjallarbrú-001…025), committed 2026-10-09. No new product features;
every slice made existing behavior stricter, safer, or better
evidenced. Full suite: **533 tests green** (was 322 at campaign
start); mypy and ruff gates clean; full-suite coverage 90%.

### Added
- `hugrgate/log.py`: library logging (`get_logger`,
  `configure_logging`, JSON formatter); silent-by-default via
  NullHandler; daemon CLI `--log-level`/`--log-json` (009)
- `hugrgate/serde.py`: neutral home for `policy_to_dict` /
  `policy_from_dict` / `result_from_dict`, breaking the former
  client↔server import cycle (021)
- `HugrGate.adecide()`: first-class async decide via
  `asyncio.to_thread` (018)
- `Backend.close()` hook + `HugrGate.close()` (best-effort) +
  `HugrGate` context manager; `BatchingQueue` async context manager
  (019)
- `ProvenanceStore(max_records=...)`: bounded memory with
  checkpoint-preserving hash-chain eviction; `verify_chain()` (015/019)
- `BackendRegistry.get_or_raise()`, `unregister()`,
  `__contains__`, `__len__` (014)
- `DecisionRecord.to_dict/from_dict`,
  `ThresholdConfig.to_dict/from_dict`,
  `NumericBand.to_dict/from_dict`, `LadderRung.from_dict`,
  `DecisionPolicy.to_dict()` (016)
- `tests/conftest.py` shared fixtures; test taxonomy
  (unit/integration/slow/gate markers) with enforcement test (023)
- Static-analysis gate: `[tool.ruff.lint]` + `lint` extra
  (`ruff>=0.8`, `coverage>=7.0`); `typecheck` extra already existed
  (022)

### Changed (behavior)
- `DecisionResult` construction now enforces: `latency_ms >= 0`,
  non-empty-string distribution keys, and
  `distribution[value] == probability` for single-value results (012)
- `validate_state`: rejects non-string keys, non-finite floats,
  nesting beyond `max_depth` (64), payloads beyond `max_bytes`
  (1 MiB); both tunable (011)
- Policy-domain config errors raise `PolicyError`, not bare
  `ValueError` (`NumericBand`, `ThresholdConfig`,
  `ordinal_cumulative_probability`) (013)
- `DecisionPolicy`: `privacy_class` restricted to
  `standard`/`strict`; `policy_from_dict`/`DecisionSpec.from_dict`
  reject unknown keys (008)
- `BackendRegistry.register`: rejects non-backends, blank names,
  and duplicate names without `replace=True` (014)
- `DecisionCache`, `BackendRegistry`, `ProvenanceStore` are now
  thread-safe (RLock); 16×250 concurrency stress tests (017)
- `BatchingQueue.stop()` no longer strands submitters: drain waits
  for in-flight batches; drain timeout fails pending futures fast
  (018)
- Internal modules import from defining submodules, never the
  package root (020)
- `HugrGateError.__str__` now `[code] message`; `QueueFull` moved
  into `hugrgate.errors` with wire round-trip (007)
- 715 safe + 68 manual ruff autofixes applied (py310
  modernization, `zip(strict=True)`, raise-from chains) (022)

### Fixed
- `recent(0)` returned the entire provenance history (015)
- `DecisionCache.stats()` raced under concurrency (017)
- Daemon batching queue could hang submitters on `stop()` (018)

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
