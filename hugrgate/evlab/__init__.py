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
from hugrgate.evlab.artifacts import (
    BundleReport,
    read_bundle,
    verify_bundle,
    write_bundle,
    zip_bundle,
)
from hugrgate.evlab.bootstrap import (
    BootstrapCI,
    bootstrap_backend_ci,
    bootstrap_mean_ci,
    bootstrap_metric_ci,
)
from hugrgate.evlab.calibration import (
    CalibrationComparison,
    HistogramBinningCalibrator,
    IdentityCalibrator,
    LabCalibrator,
    PackageCalibrator,
    TemperatureCalibrator,
    compare_backend_calibration,
    compare_calibrators,
    expected_calibration_error,
)
from hugrgate.evlab.compare import BackendComparison, compare_backends
from hugrgate.evlab.costaware import (
    CostModel,
    CostReport,
    cost_aware_evaluate,
    pareto_frontier,
)
from hugrgate.evlab.crossval import CVReport, FoldResult, cross_validate
from hugrgate.evlab.dataset import (
    ACQUISITIONS,
    COLUMN_TYPES,
    ColumnSpec,
    DatasetManifest,
    DatasetProvenance,
    DatasetRegistry,
    DatasetVersion,
    TransformStep,
    fingerprint_items,
)
from hugrgate.evlab.energy import (
    EnergyModel,
    EnergyReport,
    co2e_grams,
    energy_aware_evaluate,
)
from hugrgate.evlab.fairness import FairnessReport, fairness_evaluate
from hugrgate.evlab.gates import (
    Gate,
    GateResult,
    GateSuite,
    assert_gates,
    check_gates,
    gates_from_config,
)
from hugrgate.evlab.history import (
    HistoryStore,
    RegressionFinding,
    detect_regression,
    series_summary,
)
from hugrgate.evlab.latency import LatencyReport, latency_aware_evaluate
from hugrgate.evlab.privacy import (
    PIIReport,
    PrivacyUtilityCurve,
    PrivacyUtilityPoint,
    privacy_utility_curve,
    randomized_response_q,
    scan_dataset_pii,
)
from hugrgate.evlab.repro import (
    ReproCheck,
    ReproManifest,
    build_repro_manifest,
    check_reproducibility,
    manifest_for_run,
)
from hugrgate.evlab.robustness import (
    LabelNoise,
    Perturbation,
    RobustnessReport,
    StateDropout,
    robustness_evaluate,
)
from hugrgate.evlab.selective import (
    SelectivePoint,
    SelectiveReport,
    aurc,
    coverage_at_risk,
    oracle_aurc,
    risk_at_coverage,
    risk_coverage_curve,
    selective_evaluate,
)
from hugrgate.evlab.shift import ShiftReport, label_psi, shift_evaluate
from hugrgate.evlab.significance import (
    SignificanceResult,
    compare_paired_correctness,
    mcnemar_test,
    paired_permutation_test,
)
from hugrgate.evlab.splits import (
    SplitPlan,
    kfold_indices,
    make_splits,
    manifest_splits,
)
from hugrgate.evlab.stratified import StratifiedReport, stratified_evaluate

__all__ = [
    "ACQUISITIONS",
    "COLUMN_TYPES",
    "DEFAULT_METRICS",
    "BackendComparison",
    "BootstrapCI",
    "BundleReport",
    "CVReport",
    "CalibrationComparison",
    "ColumnSpec",
    "CostModel",
    "CostReport",
    "DatasetManifest",
    "DatasetProvenance",
    "DatasetRegistry",
    "DatasetVersion",
    "EnergyModel",
    "EnergyReport",
    "EvaluationLab",
    "Experiment",
    "FairnessReport",
    "FoldResult",
    "Gate",
    "GateResult",
    "GateSuite",
    "HistogramBinningCalibrator",
    "HistoryStore",
    "IdentityCalibrator",
    "LabCalibrator",
    "LabelNoise",
    "LatencyReport",
    "MetricSet",
    "PIIReport",
    "PackageCalibrator",
    "Perturbation",
    "PrivacyUtilityCurve",
    "PrivacyUtilityPoint",
    "RegressionFinding",
    "ReproCheck",
    "ReproManifest",
    "RobustnessReport",
    "RunRecord",
    "SelectivePoint",
    "SelectiveReport",
    "ShiftReport",
    "SignificanceResult",
    "SplitPlan",
    "StateDropout",
    "StratifiedReport",
    "TemperatureCalibrator",
    "TransformStep",
    "assert_gates",
    "aurc",
    "bootstrap_backend_ci",
    "bootstrap_mean_ci",
    "bootstrap_metric_ci",
    "build_repro_manifest",
    "check_gates",
    "check_reproducibility",
    "co2e_grams",
    "compare_backend_calibration",
    "compare_backends",
    "compare_calibrators",
    "compare_paired_correctness",
    "cost_aware_evaluate",
    "coverage_at_risk",
    "cross_validate",
    "detect_regression",
    "energy_aware_evaluate",
    "expected_calibration_error",
    "fairness_evaluate",
    "fingerprint_items",
    "gates_from_config",
    "kfold_indices",
    "label_psi",
    "latency_aware_evaluate",
    "make_splits",
    "manifest_for_run",
    "manifest_splits",
    "mcnemar_test",
    "oracle_aurc",
    "paired_permutation_test",
    "pareto_frontier",
    "privacy_utility_curve",
    "randomized_response_q",
    "read_bundle",
    "risk_at_coverage",
    "risk_coverage_curve",
    "robustness_evaluate",
    "scan_dataset_pii",
    "selective_evaluate",
    "series_summary",
    "shift_evaluate",
    "stratified_evaluate",
    "verify_bundle",
    "write_bundle",
    "zip_bundle",
]
