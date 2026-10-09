"""Ensemble intelligence — one decision from many backends. Slices 101-125.

:class:`Ensemble` composes member backends behind a single
:class:`~hugrgate.backend.Backend` interface and combines their ballots
with a registered strategy (voting, Bayesian averaging, stacking,
blending, mixture-of-experts), wrapped in disagreement handling,
reliability weighting, calibration, provenance, caching, and release
gating.
"""

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
from hugrgate.ensemble.blending import (
    Blender,
    blending_combine,
    log_loss,
    project_simplex,
)
from hugrgate.ensemble.moe import ExpertRouter, moe_combine
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
    "soft_voting",
    "hard_voting",
    "weighted_voting",
    "confidence_weighted_voting",
    "BayesianModelAverager",
    "bma_combine",
    "predictive_log_likelihood",
    "SoftmaxRegression",
    "StackingEngine",
    "stacking_combine",
    "Blender",
    "blending_combine",
    "project_simplex",
    "log_loss",
    "ExpertRouter",
    "moe_combine",
]
