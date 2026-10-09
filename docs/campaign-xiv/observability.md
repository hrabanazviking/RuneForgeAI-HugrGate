# HugrGate Observability — Campaign XIV

**Mission:** make every important decision path measurable, inspectable,
and explainable.

The `hugrgate.observability` package is the operations layer around
Campaign VI's learning-oriented telemetry: metrics, distributed
traces, structured logging, dashboards, SLOs, alerts, and explanation
reports. It is stdlib-only (the OpenTelemetry SDK is an optional
`otel` extra) and sits above `spec` / `result` / `backend` /
`policy`, provenance, privacy, and drift detection — it never reaches
into the service layer.

## The privacy law (load-bearing)

Every observability surface carries **metadata, never payload**:

- span attributes and log fields reject payload keys (`state`,
  `value`, `input`, `prompt`, `payload`, `pii`, …) with a raised
  error, not a silent drop;
- decision spans record probability *bands* and never the decision
  value or distribution;
- explanation reports redact the decision value unless
  `include_value=True` is passed explicitly;
- privacy-event metrics count violations by taxonomy code — the
  violating payload is never an argument.

## Module map

| Module | Slice | Purpose |
|---|---|---|
| `metrics` | 326 | `Counter`/`Gauge`/`Histogram` registry: validated names, fixed label sets, bounded cardinality, JSON snapshots |
| `otel` | 327 | OpenTelemetry bridge: W3C traceparent, lazy optional SDK, local-first fallback exporter |
| `trace` | 328 | `Span`, deterministic `ProbabilisticSampler`, bounded `TraceStore`, `Tracer` with `trace()`/`@traced` |
| `spans_decision` | 329 | Decision spans from spec/result/policy |
| `spans_backend` | 330 | Per-attempt backend spans with taxonomy error codes |
| `spans_routing` | 331 | Routing spans from `RouteEvent` (trace ≡ learning dataset) |
| `spans_calibration` | 332 | Calibration spans + empirical coverage validation (exact binomial CI) |
| `logschema` | 333 | Versioned append-only log event schemas, validation, JSON formatter, trace adapter |
| `prometheus` | 334 | Prometheus text exposition (0.0.4) |
| `dashboard` | 335 | `HealthDashboard`: observe → health + metrics; JSON snapshot with healthy/degraded/critical |
| `histograms` | 336 | `LatencyTracker`: ms helpers, p50/p90/p99, SLA predicate |
| `confidence` | 337 | `ConfidenceHistogram`: probability distribution, band masses |
| `abstention` | 338 | Abstentions by reason, reviews, windowed rates |
| `escalation` | 339 | Worker restarts/escalations, plugs into `Supervisor` |
| `cost` | 340 | Cost aggregation by backend/route, charge ledger |
| `energy` | 341 | `EnergyEstimator` protocol + documented coefficient model |
| `privacy_metrics` | 342 | Violation/denied-flow/redaction counts, adversarially tested |
| `alerts` | 343 | Drift alerts, rules with dedup + cooldown |
| `slo` / `slo_eval` | 344–345 | Immutable SLO definitions; burn-rate evaluator |
| `explain` | 346 | Decision explanation reports (provenance + spans) |
| `replay` | 347 | Trace replay viewer data (timeline, waterfall) |
| `load` | 348 | Load harness: the cost of watching, gated |

## Quickstart

```python
from hugrgate.observability.dashboard import HealthDashboard
from hugrgate.observability.trace import Tracer
from hugrgate.observability.spans_decision import decision_span, annotate_decision
from hugrgate.observability.prometheus import generate_latest

tracer = Tracer()
dashboard = HealthDashboard()

with decision_span(tracer, spec, policy) as span:
    result = gate.decide(spec)          # your existing call
    annotate_decision(span, spec, result, policy)
dashboard.observe(result.backend, result.latency_ms,
                  ok=result.accepted, verdict="accept")

print(dashboard.snapshot()["status"])   # healthy | degraded | critical
print(generate_latest(dashboard.registry))  # scrape me
```

## Error taxonomy

`ObservabilityError` (recoverable) is the base; `MetricError` and
`TraceError` are recoverable (a failed recording must never fail the
decision); `AlertError` is recoverable; `SLOError` is **not**
recoverable (a bad SLO definition is a configuration bug — fix it,
don't retry it). See `hugrgate/errors.py` and
`tests/test_errors.py`.

## What was hardened along the way

- `Tracer.trace` applies first-error-wins so nested span builders'
  specific taxonomy codes survive (slice 330).
- `DecisionRecord.from_decision` preserves `result.metadata`
  (`policy_verdict`, `abstain_reason`) instead of dropping it —
  provenance was losing the machine-readable verdict (slice 346).
- `ObservabilityFormatter` surfaces trace/span ids on plain records
  too, not just schema events (slice 333).

## Measurement artifacts

- `benchmarks/observability_overhead_336.json` — instrumented
  observe path: p99 14.2 µs vs 50 µs baseline (n=20000, seed=336).
- `benchmarks/observability_energy_341.json` — energy model
  provenance, determinism check, worked example (explicitly not
  hardware truth).
