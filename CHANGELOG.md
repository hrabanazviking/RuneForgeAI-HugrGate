# Changelog — HugrGate

## Unreleased — Gjallarbrú Campaign X: Privacy Fortress (slices 226–250)

Data sovereignty and enforceable information-flow constraints become
core architecture: an ordered five-class privacy ladder, field-level
sensitivity labels, a data-flow policy engine, backend trust levels
and jurisdiction metadata, local-only enforcement, a redaction
pipeline, tokenization, secret/PII detection, prompt minimization, a
remote payload compiler chokepoint, privacy-preserving and encrypted
provenance, retention and secure deletion, an encrypted cache option,
a key-provider abstraction, violation auditing, dry-run mode,
explanation reports, fuzz and exfiltration testing, a privacy
benchmark suite, and a release gate.

### Added (slice 238)
- Privacy-preserving provenance (`hugrgate.privacy_provenance`):
  per-class record builder, opt-in value fingerprints,
  `PrivacyAwareProvenanceStore`; core/ladder use it instead of
  ad-hoc redaction branches.

### Added (slice 237)
- Remote payload compiler (`hugrgate.privacy_payload`): the
  eight-stage outbound chokepoint (`RemotePayloadCompiler` /
  `RemotePayload` with audit manifest); `PrivacyGuard`
  `payload_compiler` hook + `compile_outbound`;
  `LadderRouter._attempt` compiles remote-bound state and audits
  denials as privacy skips.

### Added (slice 236)
- Prompt / data minimization (`hugrgate.privacy_minimize`):
  `minimize_state`, per-backend `MinimizationPolicy`, and
  budget-enforcing `PromptMinimizer`.

### Added (slice 235)
- PII detector interface (`hugrgate.privacy_pii`): `PIIDetector`
  interface, `RegexPIIDetector` with Luhn/SSN/IPv4 validators,
  `CompositePIIDetector`, `PIIScrubber` mask/drop actions.

### Added (slice 234)
- Secret detection hooks (`hugrgate.privacy_secrets`):
  `SecretScanner` with curated patterns + opt-in entropy heuristic,
  `scan_text`/`scan_state`, `assert_no_secrets`;
  `PrivacyGuard.check_no_secrets`. New `SecretDetected` error (code
  `secret_detected`).

### Added (slice 233)
- Tokenization / pseudonymization (`hugrgate.privacy_tokens`):
  `TokenVault` with opaque CSPRNG tokens, namespace isolation,
  revoke/clear, and export/import for encrypted persistence.

### Added (slice 232)
- Redaction pipeline v2 (`hugrgate.privacy_redact`): composable
  `Redactor` strategies (mask/pattern/hash/drop/token),
  `RedactionPipeline` with per-field and per-sensitivity strategies,
  deep metadata scrubbing; `PrivacyGuard.redact_record` hardened to
  the deep scrub.

### Added (slice 231)
- Local-only field enforcement (`hugrgate.privacy_localonly`):
  `LocalOnlyPolicy` strip/strict modes, nested-aware stripping with
  pruning, deep-copy safety; `PrivacyGuard.enforce_local_only`.
  New `LocalOnlyViolation` error (code `local_only_violation`).

### Added (slice 230)
- Jurisdiction metadata (`hugrgate.privacy_jurisdiction`):
  `JurisdictionRegistry` (fail-closed `"unknown"` default for
  undeclared remotes) + `JurisdictionPolicy`; `PrivacyGuard`
  enforces `jurisdictions_allowed` at selection/attempt time.
  New `JurisdictionViolation` error (code `jurisdiction_violation`).

### Added (slice 229)
- Backend trust levels (`hugrgate.privacy_trust`):
  `TrustAttestation` + `BackendTrustRegistry` with expiry/revocation
  and safe fallback; `PrivacyGuard(trust_registry=...)` evaluates
  class trust floors against attested trust. Trust primitives moved
  here from `hugrgate.privacy` (re-exported, no cycle).

### Added (slice 228)
- Data-flow policy engine (`hugrgate.privacy_flow`): `FlowRequest` /
  `DataFlowPolicy` / `FlowDecision` with ordered deterministic rules
  (class eligibility, trust floor, jurisdiction, field levels,
  local-only stripping) and `DataFlowDenied` error
  (`hugrgate.errors`, code `data_flow_denied`, not recoverable).

### Added (slice 227)
- Field-level sensitivity labels (`hugrgate.privacy_labels`):
  `Sensitivity` ladder, `FieldLabels` with dotted-path nested support
  and `local_only` marking, `filter_by_clearance` for
  clearance-based field filtering.

### Added (slice 226)
- Privacy classification v2: `public < standard < sensitive < strict <
  forbidden` ladder (`hugrgate.policy.DecisionPolicy.PRIVACY_CLASSES`,
  `hugrgate.privacy.PRIVACY_CLASS_ORDER` / `CLASS_SEMANTICS` /
  `TRUST_ORDER` and helpers). `PrivacyGuard` now enforces class
  semantics at selection and attempt time.

### Changed (behavior, slice 226)
- `strict`-class data now requires a `verified`-trust remote backend;
  unattested remotes are denied even when the policy allows remote
  inference. `forbidden`-class data can never reach a remote backend.
  Provenance redaction in core/ladder follows the class ladder's
  provenance mode.

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
