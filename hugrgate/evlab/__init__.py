"""Evaluation Laboratory — Gjallarbrú Campaign XV (slices 351-375).

A rigorous, reproducible evaluation system for decision quality and
system behavior, built on top of the existing benchmark machinery
(:mod:`hugrgate.bench`, :mod:`hugrgate.perfgate`,
:mod:`hugrgate.millionbench`, :mod:`hugrgate.calibration.bench`) rather
than duplicating it:

- :mod:`hugrgate.evlab.api` — Evaluation API v2: experiments, runs,
  run records (slice 351).
- :mod:`hugrgate.evlab.dataset` — dataset manifests, versioning,
  provenance (slices 352-354).
- :mod:`hugrgate.evlab.splits` — dataset split tooling (slice 355).
- :mod:`hugrgate.evlab.stratified` — stratified evaluation (slice 356).
- :mod:`hugrgate.evlab.crossval` — cross-validation harness (357).
- :mod:`hugrgate.evlab.bootstrap` — bootstrap confidence intervals (358).
- :mod:`hugrgate.evlab.significance` — significance testing (359).
- :mod:`hugrgate.evlab.compare` — paired backend comparisons (360).
- :mod:`hugrgate.evlab.calibration` — calibration-method comparisons (361).
- :mod:`hugrgate.evlab.selective` — selective-risk evaluation (362).
- :mod:`hugrgate.evlab.costaware` — cost-aware evaluation (363).
- :mod:`hugrgate.evlab.latency` — latency-aware evaluation (364).
- :mod:`hugrgate.evlab.energy` — energy-aware evaluation (365).
- :mod:`hugrgate.evlab.privacy` — privacy-aware evaluation (366).
- :mod:`hugrgate.evlab.robustness` — robustness evaluation (367).
- :mod:`hugrgate.evlab.shift` — shift evaluation (368).
- :mod:`hugrgate.evlab.fairness` — fairness measurement hooks (369).
- :mod:`hugrgate.evlab.history` — regression benchmark history (370).
- :mod:`hugrgate.evlab.artifacts` — benchmark artifact bundles (371).
- :mod:`hugrgate.evlab.repro` — reproducibility manifests (372).
- :mod:`hugrgate.evlab.gates` — evaluation CI gates (373).
- :mod:`hugrgate.evlab.report` — public benchmark report generator (374).
- :mod:`hugrgate.evlab.release` — evaluation lab release gate (375).
"""

from __future__ import annotations

from hugrgate.evlab.api import (
    DEFAULT_METRICS,
    EvaluationLab,
    Experiment,
    MetricSet,
    RunRecord,
)

__all__ = [
    "DEFAULT_METRICS",
    "EvaluationLab",
    "Experiment",
    "MetricSet",
    "RunRecord",
]
