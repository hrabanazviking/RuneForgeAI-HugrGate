# HugrGate Evaluation Laboratory

Gjallarbrú Campaign XV (slices 351–375). A rigorous, reproducible
evaluation system for decision quality and system behavior — built on
top of the existing benchmark machinery (`hugrgate.bench`,
`hugrgate.perfgate`, `hugrgate.millionbench`,
`hugrgate.calibration.bench`), not as a duplicate of it.

## Concepts

- **Experiment** (`hugrgate.evlab.api.Experiment`) — a named, seeded,
  serializable evaluation plan: dataset, backends, policy, metric set,
  tags, `max_items`.
- **EvaluationLab** (`hugrgate.evlab.api.EvaluationLab`) — registers
  experiments and executes them, returning immutable `RunRecord`s.
- **RunRecord** — one run: identity, timestamps, dataset fingerprint +
  version, policy, per-backend metrics, provenance (hugrgate version,
  platform, best-effort git SHA), privacy class.
- **MetricSet** — selects which `run_benchmark` metrics a run reports
  and admits post-hoc derived metrics over the per-backend metric dict.

## Quick start

```python
from hugrgate.evlab import EvaluationLab, Experiment

lab = EvaluationLab()  # or EvaluationLab(gate=my_gate)
lab.register_experiment(Experiment(
    name="smoke",
    dataset={"name": "smoke", "version": "1.0.0",
             "spec": {...}, "items": [{"state": {...}, "expected": "a"}]},
    backends=["rules", "logreg"],
    seed=351,
))
record = lab.run("smoke")
print(record.best("accuracy"))          # ('logreg', 0.83)
print(record.to_dict())                 # JSON-serializable
```

`lab.run("smoke", dry_run=True)` returns the execution plan without
touching any backend.

## Reproducibility

The lab reseeds the stdlib RNG per run from the experiment seed, so
any randomized lab machinery (splits, bootstraps) is reproducible.
Backend determinism is the backend's own contract. Every record
carries the dataset fingerprint (`bench.dataset_fingerprint`), the
dataset version, and a best-effort git SHA.

## Privacy

A dataset may declare `"sensitivity": "restricted"` (or
`"contains_pii": true`). Restricted data refuses to run unless the
policy's `privacy_class` is `"sensitive"` or `"strict"`. The record
always carries the effective privacy class.

## Release workflow

The capstone (`evlab.release`): `release_gate(record, gates, ...)`
renders one go/no-go `ReleaseVerdict` over a finished run — CI gates
(`evlab.gates`), regression checks against the history store
(`evlab.history`), the reproducibility manifest (`evlab.repro`),
and git-SHA provenance. Any failure holds the release with every
reason named; `assert_release()` turns a hold into `EvalGateError`
for CI. A gateless suite is refused: a release with zero quality
gates is a rubber stamp.

## Errors

- `EvalError` — bad experiment configuration or empty run. Not
  recoverable: fix the experiment, re-run.
- `EvalGateError` — a quality gate (or the release gate) failed.
  Not recoverable: change the code, the data, or the gate, re-run.
- `DatasetError` — malformed/unusable dataset. Not recoverable.

## Slice map

- 351 — Evaluation API v2 (`evlab.api`): this document's API.
- 352 — Dataset manifest standard (`evlab.dataset`).
- 353 — Dataset versioning (`evlab.dataset`).
- 354 — Dataset provenance (`evlab.dataset`).
- 355 — Dataset split tooling (`evlab.splits`).
- 356 — Stratified evaluation (`evlab.stratified`).
- 357 — Cross-validation harness (`evlab.crossval`).
- 358 — Bootstrap confidence intervals (`evlab.bootstrap`).
- 359 — Significance testing (`evlab.significance`).
- 360 — Paired backend comparisons (`evlab.compare`).
- 361 — Calibration-method comparisons (`evlab.calibration`).
- 362 — Selective-risk evaluation (`evlab.selective`).
- 363 — Cost-aware evaluation (`evlab.costaware`).
- 364 — Latency-aware evaluation (`evlab.latency`).
- 365 — Energy-aware evaluation (`evlab.energy`).
- 366 — Privacy-aware evaluation (`evlab.privacy`).
- 367 — Robustness evaluation (`evlab.robustness`).
- 368 — Shift evaluation (`evlab.shift`).
- 369 — Fairness measurement hooks (`evlab.fairness`).
- 370 — Regression benchmark history (`evlab.history`).
- 371 — Benchmark artifact bundles (`evlab.artifacts`).
- 372 — Reproducibility manifests (`evlab.repro`).
- 373 — Evaluation CI gates (`evlab.gates`).
- 374 — Public benchmark report generator (`evlab.report`).
- 375 — Evaluation Lab release gate (`evlab.release`).
