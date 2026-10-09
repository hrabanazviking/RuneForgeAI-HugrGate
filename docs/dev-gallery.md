# HugrGate Example Gallery

Every example below is a complete, runnable program. Each one is
executed end-to-end by `tests/test_deveco_442_gallery.py`, so the
gallery cannot rot: a broken example fails the suite.

Run any example with the repo venv:

```bash
venv/bin/python examples/<name>.py
```

## Learning path

| # | Example | Shows | Level |
|---|---------|-------|-------|
| 1 | `event_triage.py` | Deterministic rules → policy → fallback → provenance | Beginner |
| 2 | `policy_playbook.py` | Thresholds, review bands, privacy classes, backend allow-lists | Beginner |
| 3 | `client_policies.py` | Server-side per-client policies via `X-Client-Id` | Intermediate |
| 4 | `service_roundtrip.py` | HTTP daemon + SDK client, in-process fallback | Intermediate |
| 5 | `calibrated_triage.py` | Prior-shift calibration, ECE measurement, recalibration | Advanced |
| 6 | `drift_watch.py` | Calibration drift detection (PSI) + recalibration advisory | Advanced |
| 7 | `ladder_routing.py` | The intelligence ladder: rules → learned → abstain | Advanced |
| 8 | `benchmark_run.py` | Full benchmark harness with markdown report | Advanced |

## The examples

### 1. Event triage (`event_triage.py`)

The deterministic reference runtime, zero ML: a YAML rule set feeds
a `DecisionPolicy`, a `FallbackChain`, and full `Provenance`, all
through `HugrGate.decide()`. Security events are triaged into
`ignore` / `log` / `inspect` / `escalate`.

- **Start here** if you are new: no model training, no server.
- **Concepts:** `DecisionPolicy`, `FallbackChain`, `Provenance`.
- **Related:** `docs/concepts.md`, `docs/quickstart.md`.

### 2. Policy playbook (`policy_playbook.py`)

What `DecisionPolicy` actually does at runtime:
`minimum_probability` → abstention instead of a guess;
`review_band` → a `review` verdict distinct from accept/abstain;
`privacy_class="strict"` → raw input redacted from provenance;
`allowed_backends` → policy-level backend selection.

- **Concepts:** policy thresholds, review bands, privacy classes.
- **Related:** `docs/api.md` (policy reference).

### 3. Per-client policies (`client_policies.py`)

Server-side policy control: the daemon maps an `X-Client-Id`
header to a server-side `DecisionPolicy` loaded from JSON. The
server-side policy wins over any policy in the request body —
untrusted clients cannot talk themselves into looser thresholds.

- **Concepts:** daemon config, client identity, policy precedence.
- **Related:** `docs/api.md`.

### 4. Service round-trip (`service_roundtrip.py`)

Starts a real HugrGate daemon in a background thread, decides
over HTTP with `HugrGateClient`, then shows the automatic
in-process fallback when the daemon goes away.

- **Concepts:** `HugrGateClient`, daemon lifecycle, fallback.
- **Related:** `docs/quickstart.md`, slice 435 `hugrgate doctor`.

### 5. Calibrated triage (`calibrated_triage.py`)

End-to-end trustworthy ML decisions: synthetic security-event
data with a *prior shift* between training (over-represents
`escalate`) and deployment, a `LogisticRegressionBackend` trained
on the shifted data, multiclass ECE measured on held-out
validation, then recalibration.

- **Concepts:** prior shift, ECE, recalibration, calibration
  profiles.
- **Related:** `docs/calibration.md`.

### 6. Drift watch (`drift_watch.py`)

Calibration drift detection in action: a `DriftMonitor` fitted on
calibration-time confidences observes a shifted live window and
prints the PSI plus the recalibration advisory.

- **Concepts:** `DriftMonitor`, PSI, recalibration advisory.
- **Related:** `docs/calibration.md`.

### 7. Ladder routing (`ladder_routing.py`)

The intelligence ladder end to end on a mixed triage workload:
rules → logreg-stub → embedding prototype → abstain. Cheap
deterministic rules answer the easy cases; a tiny learned model
takes the medium ones; a hash-embedding prototype classifier
reads the texty ones; anything left over abstains instead of
guessing.

- **Concepts:** the intelligence ladder, cost-aware routing.
- **Related:** `docs/ladder.md`, `docs/backends.md`.

### 8. Benchmark run (`benchmark_run.py`)

The benchmark harness over an original dataset: runs the keyword
and uniform baselines over `benchmarks/triage_500.json`, prints
the metric table, and writes a full markdown report (tables +
ASCII reliability diagrams + methodology) to `/tmp`.

- **Concepts:** benchmarking, reliability diagrams, baselines.
- **Related:** `docs/evlab/`.

## Contributing an example

1. Put the script in `examples/`, with a docstring that starts
   with a one-line title and a `Run:` line.
2. Make it self-contained: no network, no credentials, writes
   only under `/tmp`.
3. Add a row to the table above and a section below, in learning
   order.
4. Run the gallery test — your example must exit 0 within the
   timeout.
