# Campaign XIV — Observability — Completion Report

**Slices:** 326–350 · **Branch:** `gjallarbu/campaign-xiv`
**Base:** `origin/main` @ `777d1e2` · **Date:** 2026-10-09
**Commits:** 29 · **New tests:** 168 (12 new test modules, all green)

## Mission outcome

Every important decision path is now measurable, inspectable, and
explainable through the new `hugrgate.observability` package (24
modules, stdlib-only, leaf-level imports — no cycles, no service-layer
reach). It complements Campaign VI's learning-oriented telemetry with
an operations layer: metrics, traces, structured logs, Prometheus
export, dashboards, SLOs, alerts, and explanation reports.

## Artifacts implemented

| Slice | Artifact |
|---|---|
| 326 | `observability/metrics.py` — Counter/Gauge/Histogram registry (validated names, fixed label sets, bounded cardinality); error taxonomy (`ObservabilityError`, `MetricError`, `TraceError`, `SLOError`, `AlertError`) |
| 327 | `observability/otel.py` — W3C traceparent, `OtelBridge` (lazy optional SDK, local-first fallback), `otel` extra in pyproject |
| 328 | `observability/trace.py` — privacy-gated `Span`, deterministic `ProbabilisticSampler`, bounded `TraceStore`, `Tracer` |
| 329–332 | `observability/spans_{decision,backend,routing,calibration}.py` — span builders; empirical coverage with exact Clopper-Pearson CI |
| 333 | `observability/logschema.py` — versioned append-only event schemas, `ObservabilityFormatter`, `TraceLoggerAdapter` |
| 334 | `observability/prometheus.py` — text exposition 0.0.4 |
| 335 | `observability/dashboard.py` — `HealthDashboard` with healthy/degraded/critical snapshots |
| 336 | `observability/histograms.py` + `benchmarks/observability_overhead_336.json` — **measured** p99 14.2 µs vs 50 µs baseline |
| 337 | `observability/confidence.py` — validated against seeded Beta(2,2) |
| 338–342 | `observability/{abstention,escalation,cost,energy,privacy_metrics}.py` + `benchmarks/observability_energy_341.json` (honest estimates, not meter readings) |
| 343 | `observability/alerts.py` — drift alerts with dedup + cooldown |
| 344–345 | `observability/slo.py`, `slo_eval.py` — immutable SLOs, burn-rate evaluator |
| 346 | `observability/explain.py` — explanation reports (value redacted by default) |
| 347 | `observability/replay.py` — trace replay viewer data |
| 348 | `observability/load.py` — load harness with self-verifying gate |
| 349 | `docs/campaign-xiv/` — 23 per-slice notes + `observability.md` guide |

## Test evidence

- 168 new tests, all passing; `ruff` and `mypy` clean on all new/changed code.
- Full suite: **4005 passed, 1 skipped** in 231 s. Four failures triaged:
  - `test_observability_otel.py::test_bridge_converts_error_status` — **real bug, fixed**: the fake-SDK test injected via `sys.modules`, which is silently ignored once the real `opentelemetry.trace` is imported anywhere in the process (FastAPI pulls it in). Fixed with an explicit `_otel_trace()` seam in `otel.py`; regression-proven with the real module pre-imported.
  - `test_repo_truth.py::test_audit_manifest_matches_live_tree` — manifest regenerated via `tools/audit_repo.py` (also fixed pre-existing `cache.py` LOC drift).
  - `test_cluster_backpressure.py::test_shed_load_recovers`, `test_perf_288_deadline.py::test_deadline_aware_collection_ignores_long_window` — **pre-existing flakes**: pass 3/3 in isolation, fail only under full-suite timing pressure; untouched by this campaign.
- Derived docs regenerated and gate-verified: API inventory (313 modules), architecture map (new `observability` layer), repo manifest.

## Hardenings found by the Anti-Checkbox rule

1. `Tracer.trace` is now first-error-wins — nested span builders' specific taxonomy codes survived being overwritten (slice 330).
2. `DecisionRecord.from_decision` was **dropping** `result.metadata` (`policy_verdict`, `abstain_reason`); provenance now preserves it — additive, backward-compatible (slice 346).
3. `ObservabilityFormatter` surfaces trace/span ids on plain records, not just schema events (slice 333).
4. `_export_via_sdk` gained the `_otel_trace()` seam after the suite exposed the `sys.modules`-injection flaw (slice 350).

## Benchmark / measurement findings

- Instrumented observe path: p50 6.3 µs, p99 14.2 µs per observation (n=20000, seed=336) — well inside the 50 µs baseline; artifact committed.
- Load gate: full instrumented decision path (tracer + 3 spans + dashboard) inside the 500 µs p99 budget; the harness refuses to report "zero overhead" by asserting every iteration was recorded.
- Energy numbers are coefficient estimates with recorded provenance — explicitly not hardware truth.

## Remaining debt / explicit non-claims

- The OTel SDK path is tested against a faithful fake; a live collector round-trip still needs a real deployment (marked in `otel.py`).
- `DefaultEnergyEstimator` coefficients are planning estimates; billing-grade numbers need RAPL/nvidia-smi estimators plugged into the `EnergyEstimator` protocol.
- The two flaky timing tests above predate this campaign and remain flaky.
- `benchmarks/routing_{energy,latency,stress}_*.json` get rewritten with re-measured values whenever the suite runs — side effect, reverted in this branch, not committed.

## Definition-of-done check

Implementation present and integrated · tests exist and pass · public
interfaces typed and documented · error/failure behavior deliberate
(taxonomy) · privacy considered on every surface (payload denylist,
redaction defaults, adversarial tests) · provenance/observability
integrated · docs written per slice + campaign guide. The roadmap was
not advanced merely by visiting labels: two real bugs and one
integration gap were found and fixed along the way.
