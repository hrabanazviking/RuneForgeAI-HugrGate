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
from hugrgate.ensemble.provenance import (
    find_ensemble_records,
    record_ensemble_decision,
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
    escalate,
    MinorityReport,
    audit_minority_report,
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
from hugrgate.ensemble.moe import ExpertRouter, moe_combine
from hugrgate.ensemble.explanations import explain_ensemble
from hugrgate.ensemble.membership import (
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_STANDBY,
    MembershipManager,
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
    "Ensemble",
    "EnsembleConfig",
    "STRATEGIES",
    "register_strategy",
    "get_strategy",
    "MemberVote",
    "StrategyContext",
    "Combiner",
    "DISCRETE_SPEC_TYPES",
    "normalize_weights",
    "shannon_entropy",
    "normalized_entropy",
    "break_tie",
    "require_discrete_spec",
    "complete_distribution",
    "collect_votes",
    "finalize_result",
    "batch_collect_votes",
    "STRATEGIES_BENCHMARKED",
    "benchmark_strategies",
    "benchmark_scaling",
    "write_benchmark_report",
    "demo_council",
    "regenerate_ensemble_benchmarks",
    "SaboteurBackend",
    "DropoutBackend",
    "CorruptBackend",
    "AbstainBackend",
    "SlowBackend",
    "tie_storm_members",
    "AdversarialCase",
    "run_adversarial_suite",
    "soft_voting",
    "hard_voting",
    "weighted_voting",
    "confidence_weighted_voting",
    "BayesianModelAverager",
    "bma_combine",
    "predictive_log_likelihood",
    "record_ensemble_decision",
    "find_ensemble_records",
    "explain_ensemble",
    "SoftmaxRegression",
    "StackingEngine",
    "stacking_combine",
    "Blender",
    "blending_combine",
    "project_simplex",
    "log_loss",
    "EnsembleCalibrator",
    "expected_calibration_error",
    "CachedEnsemble",
    "EnsembleCache",
    "ExpertRouter",
    "moe_combine",
    "ReliabilityTracker",
    "STATUS_ACTIVE",
    "STATUS_STANDBY",
    "STATUS_RETIRED",
    "MembershipManager",
    "vote_entropy",
    "disagreement_rate",
    "winner_margin",
    "q_statistic",
    "double_fault_rate",
    "error_disagreement_rate",
    "error_correlation",
    "diversity_summary",
    "LEVEL_NONE",
    "LEVEL_MILD",
    "LEVEL_STRONG",
    "DisagreementThresholds",
    "DisagreementReport",
    "DisagreementDetector",
    "EscalationPolicy",
    "escalate",
    "MinorityReport",
    "minority_report",
    "audit_minority_report",
    "ConsensusConfig",
    "winner_share",
    "apply_consensus",
    "maybe_apply_consensus",
    "CorrelatedPair",
    "CorrelatedErrorReport",
    "detect_correlated_errors",
]
