"""Ensemble intelligence — one decision from many backends. Slices 101-125.

:class:`Ensemble` composes member backends behind a single
:class:`~hugrgate.backend.Backend` interface and combines their ballots
with a registered strategy (voting, Bayesian averaging, stacking,
blending, mixture-of-experts), wrapped in disagreement handling,
reliability weighting, calibration, provenance, caching, and release
gating.
"""

from hugrgate.ensemble.adversarial import (
    AbstainBackend,
    AdversarialCase,
    CorruptBackend,
    DropoutBackend,
    SaboteurBackend,
    SlowBackend,
    run_adversarial_suite,
    tie_storm_members,
)
from hugrgate.ensemble.api import (
    STRATEGIES,
    Ensemble,
    EnsembleConfig,
    get_strategy,
    register_strategy,
)
from hugrgate.ensemble.averaging import (
    BayesianModelAverager,
    bma_combine,
    predictive_log_likelihood,
)
from hugrgate.ensemble.base import (
    DISCRETE_SPEC_TYPES,
    Combiner,
    MemberVote,
    StrategyContext,
    break_tie,
    collect_votes,
    complete_distribution,
    finalize_result,
    normalize_weights,
    normalized_entropy,
    require_discrete_spec,
    shannon_entropy,
)
from hugrgate.ensemble.batch import batch_collect_votes
from hugrgate.ensemble.benchmarks import (
    STRATEGIES_BENCHMARKED,
    benchmark_scaling,
    benchmark_strategies,
    demo_council,
    regenerate_ensemble_benchmarks,
    write_benchmark_report,
)
from hugrgate.ensemble.blending import (
    Blender,
    blending_combine,
    log_loss,
    project_simplex,
)
from hugrgate.ensemble.cache import CachedEnsemble, EnsembleCache
from hugrgate.ensemble.calibration import (
    EnsembleCalibrator,
    expected_calibration_error,
)
from hugrgate.ensemble.consensus import (
    ConsensusConfig,
    apply_consensus,
    maybe_apply_consensus,
    winner_share,
)
from hugrgate.ensemble.correlation import (
    CorrelatedErrorReport,
    CorrelatedPair,
    detect_correlated_errors,
)
from hugrgate.ensemble.disagreement import (
    LEVEL_MILD,
    LEVEL_NONE,
    LEVEL_STRONG,
    DisagreementDetector,
    DisagreementReport,
    DisagreementThresholds,
    EscalationPolicy,
    MinorityReport,
    audit_minority_report,
    escalate,
    minority_report,
)
from hugrgate.ensemble.diversity import (
    disagreement_rate,
    diversity_summary,
    double_fault_rate,
    error_correlation,
    error_disagreement_rate,
    q_statistic,
    vote_entropy,
    winner_margin,
)
from hugrgate.ensemble.explanations import explain_ensemble
from hugrgate.ensemble.membership import (
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_STANDBY,
    MembershipManager,
)
from hugrgate.ensemble.moe import ExpertRouter, moe_combine
from hugrgate.ensemble.provenance import (
    find_ensemble_records,
    record_ensemble_decision,
)
from hugrgate.ensemble.release import (
    CheckResult,
    ReleaseGate,
    ReleaseVerdict,
    adversarial_clean,
    benchmark_thresholds,
    diversity_floor,
    evidence_check,
    no_correlated_cliques,
)
from hugrgate.ensemble.reliability import ReliabilityTracker
from hugrgate.ensemble.stacking import (
    SoftmaxRegression,
    StackingEngine,
    stacking_combine,
)
from hugrgate.ensemble.voting import (
    confidence_weighted_voting,
    hard_voting,
    soft_voting,
    weighted_voting,
)

__all__ = [
    "DISCRETE_SPEC_TYPES",
    "LEVEL_MILD",
    "LEVEL_NONE",
    "LEVEL_STRONG",
    "STATUS_ACTIVE",
    "STATUS_RETIRED",
    "STATUS_STANDBY",
    "STRATEGIES",
    "STRATEGIES_BENCHMARKED",
    "AbstainBackend",
    "AdversarialCase",
    "BayesianModelAverager",
    "Blender",
    "CachedEnsemble",
    "CheckResult",
    "Combiner",
    "ConsensusConfig",
    "CorrelatedErrorReport",
    "CorrelatedPair",
    "CorruptBackend",
    "DisagreementDetector",
    "DisagreementReport",
    "DisagreementThresholds",
    "DropoutBackend",
    "Ensemble",
    "EnsembleCache",
    "EnsembleCalibrator",
    "EnsembleConfig",
    "EscalationPolicy",
    "ExpertRouter",
    "MemberVote",
    "MembershipManager",
    "MinorityReport",
    "ReleaseGate",
    "ReleaseVerdict",
    "ReliabilityTracker",
    "SaboteurBackend",
    "SlowBackend",
    "SoftmaxRegression",
    "StackingEngine",
    "StrategyContext",
    "adversarial_clean",
    "apply_consensus",
    "audit_minority_report",
    "batch_collect_votes",
    "benchmark_scaling",
    "benchmark_strategies",
    "benchmark_thresholds",
    "blending_combine",
    "bma_combine",
    "break_tie",
    "collect_votes",
    "complete_distribution",
    "confidence_weighted_voting",
    "demo_council",
    "detect_correlated_errors",
    "disagreement_rate",
    "diversity_floor",
    "diversity_summary",
    "double_fault_rate",
    "error_correlation",
    "error_disagreement_rate",
    "escalate",
    "evidence_check",
    "expected_calibration_error",
    "explain_ensemble",
    "finalize_result",
    "find_ensemble_records",
    "get_strategy",
    "hard_voting",
    "log_loss",
    "maybe_apply_consensus",
    "minority_report",
    "moe_combine",
    "no_correlated_cliques",
    "normalize_weights",
    "normalized_entropy",
    "predictive_log_likelihood",
    "project_simplex",
    "q_statistic",
    "record_ensemble_decision",
    "regenerate_ensemble_benchmarks",
    "register_strategy",
    "require_discrete_spec",
    "run_adversarial_suite",
    "shannon_entropy",
    "soft_voting",
    "stacking_combine",
    "tie_storm_members",
    "vote_entropy",
    "weighted_voting",
    "winner_margin",
    "winner_share",
    "write_benchmark_report",
]
