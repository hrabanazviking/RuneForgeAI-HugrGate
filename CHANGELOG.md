# Changelog — HugrGate

## Unreleased — Dawn-forge 2026-10-10: Sif's Loom, Wave A (slices 1–5 of 20)

Post-Gjallarbrú coherence weave, first five slices (coordinator interrupted;
waves B–C pending): tree hygiene — benchmark tests now write artifacts to
`tmp_path` instead of dirtying the checked-in tree, and the triage demo honors
`HUGRGATE_DEMO_DIR` so the example gallery never dirties the tree; error
quality — `hugrgate/configgen.py` suggests close-match keys on unknown daemon
config keys ("did you mean 'port'?"), and routing-component misuse now raises
the taxonomy's new `RoutingError` (also a `ValueError`, so existing
`except ValueError` callers keep working) instead of bare stdlib raises in
`hugrgate/routing/latency.py`; plus regression tests for daemon SIGINT/SIGTERM
graceful drain and demo-profile hygiene. 4 new test files; affected area
43 passed.

## Unreleased — Gjallarbrú Campaign XIX: Autonomous Optimization (slices 451–475)

Safe automatic tuning of routing, thresholds, calibration, and resource use:
the `hugrgate.autotune` package — an optimization controller with a typed
parameter store and mode lifecycle (offline/shadow/canary/applied), objective
specs (weighted/lexicographic/guarded), constraint specs, and 12 tuners
(threshold, confidence-gate with Wilson-bound guarantees, latency-budget,
cache-policy, batch-size, backend-order, ensemble-weight, calibration
selector, hardware-aware, energy-aware, cost-aware, privacy-constrained).
Safety spine: kill-switch/blast-radius/step-size/rate safety limits,
sustained-breach rollback triggers, canary leases, hash-chained optimization
provenance, run manifests with replay verification, an adversarial harness
(honest finding: 40% label noise breaks the threshold tuner — contained at
20%), a measured-improvement benchmark, and a 6-check release gate.
231 new tests; ruff and mypy clean.

## Unreleased — Gjallarbrú Campaign XIII: Decision Memory (slices 301–325)

Episodic memory for the runtime: every decision becomes a recallable,
annotatable episode — observed outcomes, verified ground truth,
similarity search, transparent retrieval, recency/frequency features,
per-backend/contract/domain aggregates, privacy-gated access,
quotas and compaction, JSONL backup, replay, counterfactuals,
memory-assisted routing and calibration, adversarial scanning, and a
benchmark suite with a checked-in baseline. Built on top of the
provenance chain (snapshots, never index references); answers the
Campaign XII unbounded-growth flag with byte accounting, quotas, and
`ProvenanceStore.estimate_bytes`.

### Added (slice 324)
- Memory benchmark suite (`hugrgate/memory/benchmarks.py`,
  `tests/test_memory_benchmarks.py`, `benchmarks/memory_bench.json`
  baseline): seeded workload measuring record (~60us mean),
  attach_outcome (~40us), find (~82ms over 2000 episodes),
  recall (~100ms), export+import (~233ms), estimate_bytes (~32ms);
  artifact save/load/compare with a CLI that never overwrites the
  baseline on `--compare`.

### Added (slice 323)
- Memory adversarial scanning (`hugrgate/memory/adversarial.py`,
  `tests/test_memory_adversarial.py`): outcome-flooding, chronology
  violation, duplicate-flood, timestamp-anomaly, and label-conflict
  detectors with severity-graded findings; detection only, the
  operator decides the response.

### Added (slice 322)
- Memory-assisted calibration
  (`hugrgate/memory/assisted_calibration.py`,
  `tests/test_memory_assisted_calibration.py`): PAVA isotonic
  recalibration maps from labeled episodes, Brier score and ECE
  metrics, chronological fit/validate split. Validated on controlled
  miscalibrated data (n=2000, seeded): ECE 0.1497 -> 0.0541, Brier
  0.2693 -> 0.2395.

### Added (slice 321)
- Memory-assisted routing (`hugrgate/memory/assisted_routing.py`,
  `tests/test_memory_assisted_routing.py`): `advise_route()`
  recommends the candidate backend with the best historical success on
  similar decisions, abstaining explicitly when history is
  insufficient.

### Added (slice 320)
- Historical counterfactuals (`hugrgate/memory/counterfactuals.py`,
  `tests/test_memory_counterfactuals.py`): per-backend and per-value
  success estimates over similarity-gated episodes with Wilson score
  intervals and sufficient-data flags; assumptions stated explicitly.

### Added (slice 319)
- Memory replay (`hugrgate/memory/replay.py`,
  `tests/test_memory_replay.py`): re-runs stored episodes through a
  caller-supplied `decide()` function; value-match rate, mean absolute
  probability drift, per-episode mismatches, counted (never fatal)
  errors; specs deep-copied so policies cannot mutate history.

### Added (slice 318)
- Memory export/import (`hugrgate/memory/io.py`,
  `tests/test_memory_io.py`): versioned JSONL envelopes for episodes
  and compaction summaries; id-preserving restore with duplicate
  skipping, corrupt-line reports, strict mode, unknown-schema
  rejection. `Episode.from_dict()` and
  `DecisionHistory.import_episode()`.

### Added (slice 317)
- Memory compaction (`hugrgate/memory/compaction.py`,
  `tests/test_memory_compaction.py`): rolls old episodes into
  `CompactionSummary` aggregates, purges the raw episodes, stores
  summaries on the history; ground-truth-bearing episodes spared by
  default.

### Added (slice 316)
- Memory retention controls (`hugrgate/memory/retention.py`,
  `tests/test_memory_retention.py`): TTL per privacy class (reusing
  `privacy_retention` defaults), episode-count and byte quotas,
  `enforce_quotas()` / `check_quota()`, `MemoryQuotaExceeded` on
  unsatisfiable quotas; `DecisionHistory.purge()` primitive and
  `ProvenanceStore.estimate_bytes()` — the direct answer to the
  Campaign XII +1.3 GB unbounded-growth flag.

### Added (slice 315)
- Memory privacy controls (`hugrgate/memory/access.py`,
  `tests/test_memory_access.py`): owner/analyst/auditor roles over the
  privacy ladder, redacted read views, owner-only writes via
  `GuardedHistory`; adversarial negative tests for denied reads,
  denied writes, role escalation, and view isolation.

### Added (slice 314)
- Domain history profiles (`hugrgate/memory/domain_profiles.py`,
  `tests/test_memory_domain_profiles.py`): per-domain aggregates —
  volume, acceptance, outcomes, top backends, spec-type mix, mean
  probability, decay-weighted activity.

### Added (slice 313)
- Contract history features (`hugrgate/memory/contract_history.py`,
  `tests/test_memory_contract_history.py`): per-contract track
  records grouped by `contract_id` (or synthetic spec-shape keys);
  hardened `privacy_preserving_record` to propagate `contract_id`
  across all privacy modes — it was silently dropped, making contract
  history impossible.

### Added (slice 312)
- Backend history features (`hugrgate/memory/backend_history.py`,
  `tests/test_memory_backend_history.py`): per-backend counts,
  acceptance rate, outcome distribution, success rate (`None` when
  unlabeled), raw and decay-weighted probability means, latency,
  models seen.

### Added (slice 311)
- Outcome-conditioned retrieval
  (`hugrgate/memory/conditioned.py`,
  `tests/test_memory_conditioned.py`): recall filtered by outcome
  kind with strict unknown-exclusion and a ground-truth-agreement
  gate; additive `episodes=` subset parameter on `retrieve()`.

### Added (slice 310)
- Frequency features (`hugrgate/memory/frequency.py`,
  `tests/test_memory_frequency.py`): `count_by()` with pluggable key
  functions (backend, model, backend+value, outcome kind); raw and
  decay-weighted counts, first/last seen, per-outcome breakdowns.

### Added (slice 309)
- Recency features (`hugrgate/memory/recency.py`,
  `tests/test_memory_recency.py`): time-since-last-similar, last
  outcome kind, head-of-history success/failure streaks, raw and
  decay-weighted similar counts, mean similarity.

### Added (slice 308)
- Time-decay weighting (`hugrgate/memory/decay.py`,
  `tests/test_memory_decay.py`): shared exponential-decay math
  (`decay_weight`, `half_life_for_horizon`, `effective_count`,
  `decayed_mean`); `retrieval.py` refactored onto it.

### Added (slice 307)
- Contextual memory policies (`hugrgate/memory/policies.py`,
  `tests/test_memory_policies.py`): ordered record/drop/redact rules
  with built-in factories (`drop_forbidden`, `redact_above`,
  `drop_backend`, `record_only_backend`, `drop_unaccepted`); policy
  hook in `DecisionHistory.record()`; `EpisodeLike`/`HistoryLike`
  protocols keep the import graph acyclic.

### Added (slice 306)
- Decision retrieval (`hugrgate/memory/retrieval.py`,
  `tests/test_memory_retrieval.py`): transparent
  similarity+recency+outcome scoring with `RetrievalResult` score
  breakdowns and `explain()`; `recall()` convenience.

### Added (slice 305)
- Historical similarity search (`hugrgate/memory/similarity.py`,
  `tests/test_memory_similarity.py`): auditable sparse feature
  vectors, exact cosine similarity, top-k `most_similar` with
  shared-feature explanations and recency tie-breaks.

### Added (slice 304)
- Ground-truth attachment (`hugrgate/memory/groundtruth.py`,
  `tests/test_memory_groundtruth.py`): verified labels with
  immutable-once-set semantics and a supersede audit trail;
  `outcome_agrees()` comparability and
  `DecisionHistory.consistency_report()`.

### Added (slice 303)
- Outcome attachment (`hugrgate/memory/outcomes.py`,
  `tests/test_memory_outcomes.py`): frozen `Outcome` value objects
  (kind/score/observed_at/note/latency) and
  `DecisionHistory.attach_outcome()` with an overwrite guard.

### Added (slice 302)
- Queryable provenance store (`hugrgate/memory/query.py`,
  `tests/test_memory_query.py`): typed `MemoryQuery`
  filter/sort/paginate language, `DecisionHistory.find()`,
  `ProvenanceStore.scan()` hardening, and the `find_in_provenance`
  adapter (memory-only filters raise instead of being silently
  ignored).

### Added (slice 301)
- Decision history API (`hugrgate/memory/`, `history.py`,
  `tests/test_memory_history.py`): `Episode` snapshots and the
  append-mostly thread-safe `DecisionHistory` (record/get/recent/
  count/by_request_hash/episodes_between/clear/
  import_from_provenance/estimate_bytes, `max_episodes` eviction);
  new `MemoryError` / `MemoryQuotaExceeded` / `MemoryAccessDenied`
  taxonomy entries.

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

### Added (slice 250)
- Privacy Fortress release gate (`tests/test_privacy_fortress_gate.py`,
  gate-marked): asserts all 25 slices' artifacts — module imports,
  slice docs, taxonomy rows, CHANGELOG coverage, error taxonomy,
  plus end-to-end holds (exfil suite, audit chain, sealed
  round-trip, dry-run) and the stdlib-only crypto contract.

### Added (slice 249)
- Privacy benchmark suite (`benchmarks/privacy_bench_249.py` +
  `benchmarks/privacy_bench_249.json`): real per-operation
  latencies for the 10 privacy pipeline stages (payload compile
  ~2.5ms mean, everything else sub-ms).

### Added (slice 248)
- Exfiltration simulation (`hugrgate.privacy_exfil`):
  `ExfilSimulator` red-teams a guard configuration with 7
  attacker scenarios (blocked/neutralized/allowed verdicts);
  fixed a real bug where attempt labels never reached the
  payload compiler.

### Added (slice 247)
- Privacy fuzz tests (`tests/test_privacy_fuzz.py`): 15
  stdlib-seeded property tests. Found and fixed a real gap:
  the secret scanner missed OpenAI-style `sk-` keys — added
  the `openai_key` pattern plus regression test.

### Added (slice 246)
- Privacy explanation reports (`hugrgate.privacy_explain`):
  `PrivacyExplainer` turns denials, dry-run reports, and
  provenance records into plain-language what/why/what-to-do
  reports with per-code remediation.

### Added (slice 245)
- Privacy dry-run mode (`hugrgate.privacy_dryrun`):
  `PrivacyDryRun(guard).evaluate(...)` simulates the outbound
  pipeline stage-by-stage and returns a `DryRunReport` with a
  `summary()` — no execution, no mutation, no raises.

### Added (slice 244)
- Policy violation audit (`hugrgate.privacy_audit`):
  append-only hash-chained `PrivacyAuditLog` with `FileAuditSink`;
  `PrivacyGuard(audit_log=...)` records every denial (backend
  blocks, jurisdiction, local-only strict, secret detection).

### Added (slice 243)
- Key-provider abstraction (`hugrgate.privacy_keys`):
  `KeyProvider` interface, env/file/ephemeral/rotating
  providers, HKDF `derive_key`, provider-built cache/store
  constructors. New `KeyProviderError` error (code
  `key_provider_error`).

### Added (slice 242)
- Encrypted provenance option: `SealedProvenanceStore`
  (`hugrgate.privacy_provenance`) — sealed record bodies, plaintext
  chain index, tamper-evident `verify_chain`, chain-safe purge.

### Added (slice 241)
- Encrypted cache option (`hugrgate.privacy_crypto`): stdlib
  `SealedBox` authenticated encryption + HKDF, and
  `EncryptedDecisionCache` with sealed entries, fail-closed
  tamper handling, and retention TTL caps. New `SealError` error
  (code `seal_error`).

### Added (slice 240)
- Secure deletion hooks (`hugrgate.privacy_deletion`):
  `shred_bytes`, `SecureBuffer`, `SecureDeleter` with
  `DeletionReceipt`, `CryptoShredder` for key-destruction deletion.

### Added (slice 239)
- Retention policies (`hugrgate.privacy_retention`): per-class
  maximum ages, `purge_expired` with `on_purge` hook,
  `ProvenanceStore.purge` (chain-safe), `DecisionCache.put`
  `retention=` TTL capping.

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
