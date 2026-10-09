# SURGE 50-Slice Roadmap — RuneForgeAI-HugrGate

**Commissioned:** 2026-10-09, Volmarr's coding surge, GOAL 5
**Vision:** Open-source, local-first, model-agnostic probabilistic decision runtime.
*"Deterministic where possible. Probabilistic where useful. Generative only where necessary."*
**Method:** Mythic Engineering 6-phase per slice — Skald → Rúnhild → Eldra → Sólrún → Védis → Scribe
**Source material:** README.md, HugrGate_ROADMAP.md (16 phases), HugrGate_Plundering_Guide.md, MYTHIC_ENGINEERING.md

Every slice is production-quality: real code, real tests, real docs. No stubs, no TODOs.

---

## PART A — FOUNDATION (Slices 1–10)

### Slice 1: Project Scaffolding
`pyproject.toml` (hatchling), `hugrgate/` package layout, `venv`, `.gitignore`,
`LICENSE` (Apache-2.0, already present), `CONTRIBUTING.md`, `CLEAN_ROOM.md`,
`LEGAL-NOTES.md`, `PROVENANCE.md`, `docs/adr/` with ADR-001 (project scope).
Tests: package imports cleanly.

### Slice 2: DecisionSpec — Categorical
`hugrgate/spec.py`: `DecisionSpec` dataclass with `type="categorical"`,
`options: list[str]` (≥2, unique). Validation: rejects empty/duplicate options.
JSON/YAML serialization round-trip. Tests: valid/invalid specs.

### Slice 3: DecisionSpec — Binary, Ordinal, Numeric, Multilabel
Extend `spec.py`: `binary` (statement: str), `ordinal` (levels: ordered list),
`numeric` (minimum/maximum floats), `multilabel` (labels: list). Each with
strict validation. Tests: one per type + cross-type rejection.

### Slice 4: DecisionResult
`hugrgate/result.py`: `DecisionResult` with `value`, `probability` (0..1),
`distribution` (dict, sums ≈1), `uncertainty`, `accepted` (bool),
`backend`, `model`, `latency_ms`, `calibration_profile`, `fallback_used`,
`metadata` (dict). Invariants enforced: probability in [0,1], distribution
keys match spec options. Tests: construction, invariant violations raise.

### Slice 5: Policy Engine
`hugrgate/policy.py`: `DecisionPolicy` with `minimum_probability`,
`maximum_latency_ms`, `remote_inference` (bool, default False),
`allowed_backends`, `preferred_backends`, `fallback_behavior`
("abstain"|"safe_default"|"escalate"), `privacy_class`,
`max_cost`. `evaluate(result) → accepted: bool`. Tests: threshold logic.

### Slice 6: Backend Interface
`hugrgate/backend.py`: `Backend` ABC with `capabilities()`, `supports(spec)`,
`evaluate(state, spec, context)`, `health()`. Optional: `warmup()`, `batch()`,
`calibration_info()`, `estimated_latency()`, `estimated_cost()`,
`privacy_properties()`, `hardware_requirements()`. `BackendRegistry`:
register/find/list by name and capability. Tests: ABC enforcement, registry.

### Slice 7: Validation Layer
`hugrgate/validation.py`: validate `state` (JSON-serializable dict),
validate spec-result consistency (result value ∈ spec options),
validate distribution sums to 1 (±1e-6), validate probability bounds.
`ValidationError` with machine-readable codes. Tests: each violation.

### Slice 8: Core Runtime — decide()
`hugrgate/core.py`: `HugrGate.decide(state, spec, policy, context)`:
validate → select backend → evaluate → apply policy → return result.
Never returns a value outside the spec's decision space. Structured errors.
Tests: end-to-end with a stub backend.

### Slice 9: Provenance Records
`hugrgate/provenance.py`: `DecisionRecord` capturing request hash, spec,
backend, model version, calibration profile, probability, policy, threshold,
result, latency, timestamp. Optional raw-input redaction for privacy.
`ProvenanceStore`: append/query by hash/time. Tests: record/retrieve/redact.

### Slice 10: Error Taxonomy
`hugrgate/errors.py`: `HugrGateError` base; `SpecError`, `PolicyError`,
`BackendError`, `BackendUnavailable`, `CalibrationError`, `TimeoutError`,
`PrivacyViolation`, `Abstention`. Each with code, message, recoverability
hint. Tests: hierarchy, catching.

---

## PART B — DETERMINISTIC CORE (Slices 11–20)

### Slice 11: Rule Backend — Predicates
`hugrgate/backends/rules.py`: `RuleBackend` evaluating predicate rules:
`{"if": {"field": "temperature", "gt": 90}, "then": "critical",
"confidence": 0.99}`. Operators: eq, ne, gt, gte, lt, lte, in, contains,
exists. First-match wins. Tests: each operator, match/no-match.

### Slice 12: Rule Backend — Decision Tables
Extend rules: decision-table format (rows of conditions → outcome),
default rule, rule priority ordering. YAML-loadable rule sets.
Tests: table evaluation, priority, default.

### Slice 13: Rule Backend — Confidence & Distribution
Rules emit calibrated confidence → full distribution over options
(winner gets confidence, remainder split uniformly). `supports()`:
categorical, binary, ordinal. Tests: distribution sums to 1.

### Slice 14: Fallback Engine
`hugrgate/fallback.py`: `FallbackChain`: ordered backends;
on `BackendError`/`TimeoutError`, try next; exhausted → policy's
`fallback_behavior` (safe_default value / abstain / escalate).
Provenance records `fallback_used=true` + chain trace. Tests: failover.

### Slice 15: Abstention
`hugrgate/abstain.py`: `Abstention` result type (value=None,
accepted=False, reason). Policy `review_between` band → "review" outcome
distinct from abstain. Tests: below-threshold abstains, band reviews.

### Slice 16: Thresholding
`hugrgate/threshold.py`: per-option thresholds, ordinal cumulative
thresholds ("at least moderate"), numeric band thresholds.
`apply_thresholds(result, policy)`. Tests: each threshold type.

### Slice 17: Backend Health Scoring
`hugrgate/health.py`: `HealthMonitor`: tracks per-backend latency p50/p99,
error rate, consecutive failures; `score()` 0..1; quarantine below
threshold; auto-recover on success. Tests: scoring, quarantine, recovery.

### Slice 18: Circuit Breaker
`hugrgate/circuit.py`: per-backend circuit breaker (closed/open/half-open),
failure threshold, reset timeout, half-open probe. Integrates with
FallbackChain. Tests: trip, reset, probe.

### Slice 19: Timeouts & Cancellation
`hugrgate/timeout.py`: per-decision deadline enforcement via threads;
`TimeoutError` on breach; backend `evaluate` wrapped with deadline =
min(policy.max_latency, backend estimate × headroom). Tests: slow backend
times out, fast backend unaffected.

### Slice 20: Deterministic Reference Runtime (Milestone)
Integration: `HugrGate` + `RuleBackend` + policy + fallback + provenance,
fully working with zero ML. Example: event triage
(ignore/log/inspect/escalate). `examples/event_triage.py`.
Tests: end-to-end milestone test. **This is the MVP core.**

---

## PART C — CLASSICAL ML & CALIBRATION (Slices 21–30)

### Slice 21: Feature Preprocessing Contract
`hugrgate/features.py`: `FeatureExtractor` interface:
`extract(state) → dict[str, float]`; `NumericEncoder`, `CategoricalEncoder`
(one-hot), `TextLengthEncoder`, `MissingValuePolicy`. Composable pipeline.
Tests: each encoder, pipeline composition.

### Slice 22: Logistic Regression Backend
`hugrgate/backends/logreg.py`: trains on `(features, label)` pairs,
`predict_proba` → distribution. Model manifest (feature names, classes,
trained_at). Save/load via pickle+manifest. `supports()`: categorical,
binary. Tests: train/predict/save/load round-trip.

### Slice 23: Random Forest Backend
`hugrgate/backends/forest.py`: same contract as logreg, using
`sklearn.ensemble.RandomForestClassifier`. Exposes feature importances
in `metadata`. Tests: parity with logreg contract.

### Slice 24: Gradient Boosting Backend
`hugrgate/backends/boosting.py`: `HistGradientBoostingClassifier`.
Early-stopping config. Tests: contract parity.

### Slice 25: Model Manifests & Registry
`hugrgate/models.py`: `ModelManifest` (name, version, backend, spec type,
features, classes, trained_at, metrics); `ModelStore`: disk-backed
registry, versioned, integrity hash. Tests: store/retrieve/verify.

### Slice 26: Calibration — Platt Scaling
`hugrgate/calibration/platt.py`: sigmoid fit on validation scores
(independent implementation per Plundering Guide Law 1).
`Calibrator` interface: `fit(scores, labels)`, `calibrate(score)`.
Tests: calibration improves Brier on synthetic miscalibrated data.

### Slice 27: Calibration — Isotonic & Temperature
`platt.py` siblings: `isotonic.py` (PAV algorithm, independent impl),
`temperature.py` (single-parameter scaling). `CalibratorRegistry`.
Tests: each improves calibration; temperature preserves ranking.

### Slice 28: Calibration Metrics
`hugrgate/calibration/metrics.py`: Brier score, log loss, expected
calibration error (ECE), maximum calibration error (MCE),
reliability diagram data (bins). Tests: known values on synthetic data.

### Slice 29: Calibration Profiles
`hugrgate/calibration/profiles.py`: `CalibrationProfile`: named,
versioned (backend + calibrator + fitted params + metrics + dataset hash).
Stored separately from model weights. `result.calibration_profile`
populated. Tests: profile save/load/attach.

### Slice 30: Calibrated Classifier (Milestone)
Integration: ML backend → calibrator → calibrated `DecisionResult`
with meaningful probabilities. `examples/calibrated_triage.py`:
train on synthetic event data, calibrate, decide with thresholds.
Tests: ECE below uncalibrated baseline. **Milestone: trustworthy AI decisions
in milliseconds.**

---

## PART D — INTELLIGENCE LADDER (Slices 31–40)

### Slice 31: Ladder Router
`hugrgate/ladder.py`: `LadderRouter`: ordered backend cascade;
each step declares `min_confidence`; if result below → next rung;
exhausted → abstain. Configurable per spec type. Auditable:
provenance logs each rung attempted. Tests: easy case stops at rung 1,
hard case climbs.

### Slice 32: Confidence-Gated Escalation
Extend ladder: per-rung latency budgets; skip rungs whose
`estimated_latency` exceeds remaining budget; privacy gate
(remote rungs require `policy.remote_inference=true`).
Tests: budget/privacy pruning.

### Slice 33: Embedding Backend — Prototype Classifier
`hugrgate/backends/embedding.py`: `Embedder` interface
(`embed(texts) → vectors`); `PrototypeBackend`: class prototypes =
mean embedding of labeled examples; cosine similarity → softmax
distribution. Ships with a tiny built-in hash-embedding (no model
download) for offline use. Tests: prototype classification accuracy.

### Slice 34: NLI Backend
`hugrgate/backends/nli.py`: `NLIBackend`: statement + premise →
entailment probability via open NLI model (transformers, optional dep);
graceful `BackendUnavailable` when model missing. Constrained to
`binary` specs ("statement supported by state"). Tests: with mock NLI.

### Slice 35: Local LLM Backend — Constrained Decoding
`hugrgate/backends/llm.py`: `LLMBackend`: open-weight local model
(llama.cpp-compatible via optional adapter); **constrained decoding**:
only spec-valid tokens allowed (categorical → option tokens;
binary → yes/no). Token budget, timeout. Never emits invalid values.
Tests: constrained output validity with mock engine.

### Slice 36: Backend Capability Negotiation
`hugrgate/negotiate.py`: `select_backend(spec, policy, registry)`:
filters by `supports()`, privacy, latency, health score; ranks by
historical accuracy + calibration; returns ordered candidate list.
Tests: selection logic under constraints.

### Slice 37: Batch Inference
`Backend.batch(states, spec, context) → list[DecisionResult]`:
default sequential; backends override for vectorized inference.
`HugrGate.decide_batch()`. Tests: batch == sequential results.

### Slice 38: Caching Layer
`hugrgate/cache.py`: `DecisionCache`: request-hash → result, TTL,
max size, privacy-aware (never cache when `privacy_class` forbids).
Invalidated on model/calibration change. Tests: hit/miss/invalidation.

### Slice 39: Full Ladder Integration (Milestone)
`examples/ladder_routing.py`: rules → logreg → embedding → (NLI/LLM
if available) → abstain. Demonstrates "least expensive sufficient
intelligence" on a mixed workload. Tests: routing decisions auditable.
**Milestone: the intelligence ladder works end to end.**

### Slice 40: Privacy Enforcement
`hugrgate/privacy.py`: `PrivacyGuard`: `remote_inference: forbidden`
blocks remote backends at selection time (not just policy);
data-flow audit: provenance never includes raw state when redacted;
`PrivacyViolation` raised on attempt. Tests: forbidden remote blocked.

---

## PART E — SERVICE & ECOSYSTEM (Slices 41–50)

### Slice 41: Local HTTP API
`hugrgate/server.py`: FastAPI app: `POST /decide`, `GET /health`,
`GET /backends`, `GET /models`. Request/response = spec/result JSON.
Localhost-only default. Tests: via TestClient.

### Slice 42: Service Mode
`hugrgate/daemon.py`: long-running daemon: Unix socket + localhost HTTP,
model warm pool, request batching, per-client policies, memory limits,
graceful shutdown. `hugrgate-server` entry point. Tests: daemon lifecycle.

### Slice 43: Python SDK
`hugrgate/client.py`: `HugrGateClient`: `decide()` over HTTP/IPC with
same interface as in-process; auto-fallback to in-process.
Tests: client ↔ server round-trip.

### Slice 44: CLI
`hugrgate/cli.py`: `hugrgate decide --spec spec.yaml --state state.json`,
`hugrgate backends`, `hugrgate calibrate`, `hugrgate serve`,
`hugrgate bench`. Entry point `hugrgate`. Tests: CLI invocations.

### Slice 45: Benchmark Harness
`hugrgate/bench.py`: `Benchmark`: dataset → backends → metrics
(accuracy, Brier, ECE, latency p50/p99, throughput). JSON report.
Tests: harness runs on synthetic data.

### Slice 46: Original Benchmark Datasets
`benchmarks/`: three original datasets (built for HugrGate, not copied):
`intent_500` (support-ticket intent), `urgency_500` (event urgency),
`triage_500` (security-event triage). Builder scripts + checksums.
Tests: dataset integrity.

### Slice 47: Benchmark Report
`hugrgate/bench_report.py`: markdown report from benchmark JSON:
tables, reliability diagrams (ASCII), hardware/methodology block.
`examples/benchmark_run.py`. Tests: report generation.

### Slice 48: Calibration Drift Detection
`hugrgate/drift.py`: `DriftMonitor`: compares live prediction
distribution vs. calibration-time; PSI (population stability index);
alerts when drift exceeds threshold; triggers recalibration advisory.
Tests: drift detected on shifted data.

### Slice 49: Documentation & Examples
`docs/`: `quickstart.md`, `concepts.md`, `backends.md`, `calibration.md`,
`ladder.md`, `api.md`, `clean-room.md`. `examples/`: 5 worked examples.
README "Current Status" updated from icebox → alpha. Tests: docs build
(mkdocs or plain markdown lint).

### Slice 50: Packaging & Release Readiness
`pyproject.toml` final: entry points, classifiers, optional extras
(`ml`, `onnx`, `nli`, `llm`, `server`, `bench`). `CHANGELOG.md`.
Release checklist executed (naming search, license audit, clean-room
review). Version 0.1.0. Tests: `pip install .` in fresh venv + smoke test.
**Milestone: HugrGate is real. The icebox is empty.**

---

## Execution Batches

- **Batch A:** Slices 1–10 (foundation) — coordinator + subagent A
- **Batch B:** Slices 11–20 (deterministic core) — subagent B
- **Batch C:** Slices 21–30 (classical ML + calibration) — subagent C
- **Batch D:** Slices 31–40 (intelligence ladder) — subagent D
- **Batch E:** Slices 41–50 (service & ecosystem) — subagent E

Each batch: independent modules, minimal cross-batch coupling (via
`spec.py`, `result.py`, `backend.py` contracts from Batch A).
