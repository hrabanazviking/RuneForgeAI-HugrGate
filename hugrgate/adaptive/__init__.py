"""Adaptive routing (Campaign VI) — learn which inference path fits each workload.

Where Campaign III's ``hugrgate.routing`` *plans* routes, this package
*learns* them: telemetry, outcome feedback, contextual bandits, offline
policy learning, multi-objective trade-offs, competence profiles,
safe exploration, shadow evaluation, counterfactual analysis, rollback,
versioning, explanations, drift detection, and a benchmark harness.

The package is stdlib-only and sits above the contracts layer
(``spec`` / ``result`` / ``backend`` / ``policy``), the feature
contract (``features``), provenance, privacy, and drift detection —
it never reaches into the service layer.
"""

from hugrgate.adaptive.telemetry import (
    SCHEMA_VERSION as TELEMETRY_SCHEMA_VERSION,
    RouteEvent,
    TelemetryStore,
)
from hugrgate.adaptive.feedback import (
    OUTCOME_LABELS,
    OutcomeRecord,
    OutcomeFeedbackAPI,
)
from hugrgate.adaptive.delayed import (
    DelayedLabel,
    DelayedLabelIngestion,
    SweepReport,
)
from hugrgate.adaptive.router_features import (
    SPEC_TYPES as ROUTER_SPEC_TYPES,
    RouteContext,
    RouterFeatureExtractor,
)
from hugrgate.adaptive.bandit import (
    BanditDecision,
    ContextualBanditAdapter,
)
from hugrgate.adaptive.offline import (
    LearningDiagnostics,
    OfflinePolicyLearning,
)
from hugrgate.adaptive.cost_quality import (
    RoutingCandidate,
    RouteObjective,
    CostQualityObjective,
)
from hugrgate.adaptive.latency_quality import (
    LatencyMeasurement,
    LatencyQualityObjective,
    measure_latency,
    compare_to_baseline,
)
from hugrgate.adaptive.energy_quality import (
    DEFAULT_LOCAL_WATTS,
    DEFAULT_REMOTE_WATTS,
    EnergyMeasurement,
    EnergyQualityObjective,
    estimate_energy_wh,
    measure_energy,
)
from hugrgate.adaptive.privacy_objective import (
    PrivacyConstrainedObjective,
)
from hugrgate.adaptive.multiobjective import (
    MODES as MULTIOBJECTIVE_MODES,
    MultiObjectiveRouter,
    pareto_frontier,
    dominates,
)
from hugrgate.adaptive.competence import (
    CompetenceProfile,
    BackendCompetenceProfiles,
    wilson_lower_bound,
)
from hugrgate.adaptive.domain_competence import (
    UNKNOWN_DOMAIN,
    domain_of_spec,
    domain_of_event,
    PerDomainCompetence,
)
from hugrgate.adaptive.contract_competence import (
    contract_of_spec,
    contract_of_event,
    PerContractCompetence,
)
from hugrgate.adaptive.coldstart import (
    ColdStartRouting,
)
from hugrgate.adaptive.exploration import (
    ExplorationConfig,
    ExplorationControls,
)
from hugrgate.adaptive.safe_exploration import (
    SafeChoice,
    SafeExploration,
)
from hugrgate.adaptive.shadow import (
    ShadowDivergence,
    RouterShadowMode,
)
from hugrgate.adaptive.counterfactual import (
    ESTIMATORS as COUNTERFACTUAL_ESTIMATORS,
    PolicyValueEstimate,
    CounterfactualEvaluator,
)
from hugrgate.adaptive.rollback import (
    Checkpoint,
    RouterRollback,
)
from hugrgate.adaptive.versioning import (
    PolicyVersion,
    AdaptivePolicyVersioning,
    digest_state,
)
from hugrgate.adaptive.explanations import (
    FeatureContribution,
    RouteExplanation,
    AdaptiveRouteExplainer,
)
from hugrgate.adaptive.drift_detect import (
    AdaptiveDriftReport,
    AdaptiveRouteDriftDetector,
)
from hugrgate.adaptive.benchmark import (
    POLICIES as BENCHMARK_POLICIES,
    BenchmarkArtifact,
    AdaptiveRoutingBenchmark,
    default_scenario,
)

__all__ = [
    "TELEMETRY_SCHEMA_VERSION",
    "RouteEvent",
    "TelemetryStore",
    "OUTCOME_LABELS",
    "OutcomeRecord",
    "OutcomeFeedbackAPI",
    "DelayedLabel",
    "DelayedLabelIngestion",
    "SweepReport",
    "ROUTER_SPEC_TYPES",
    "RouteContext",
    "RouterFeatureExtractor",
    "BanditDecision",
    "ContextualBanditAdapter",
    "LearningDiagnostics",
    "OfflinePolicyLearning",
    "RoutingCandidate",
    "RouteObjective",
    "CostQualityObjective",
    "LatencyMeasurement",
    "LatencyQualityObjective",
    "measure_latency",
    "compare_to_baseline",
    "DEFAULT_LOCAL_WATTS",
    "DEFAULT_REMOTE_WATTS",
    "EnergyMeasurement",
    "EnergyQualityObjective",
    "estimate_energy_wh",
    "measure_energy",
    "PrivacyConstrainedObjective",
    "MULTIOBJECTIVE_MODES",
    "MultiObjectiveRouter",
    "pareto_frontier",
    "dominates",
    "CompetenceProfile",
    "BackendCompetenceProfiles",
    "wilson_lower_bound",
    "UNKNOWN_DOMAIN",
    "domain_of_spec",
    "domain_of_event",
    "PerDomainCompetence",
    "contract_of_spec",
    "contract_of_event",
    "PerContractCompetence",
    "ColdStartRouting",
    "ExplorationConfig",
    "ExplorationControls",
    "SafeChoice",
    "SafeExploration",
    "ShadowDivergence",
    "RouterShadowMode",
    "PolicyValueEstimate",
    "COUNTERFACTUAL_ESTIMATORS",
    "CounterfactualEvaluator",
    "Checkpoint",
    "RouterRollback",
    "PolicyVersion",
    "AdaptivePolicyVersioning",
    "digest_state",
    "FeatureContribution",
    "RouteExplanation",
    "AdaptiveRouteExplainer",
    "AdaptiveDriftReport",
    "AdaptiveRouteDriftDetector",
    "BENCHMARK_POLICIES",
    "BenchmarkArtifact",
    "AdaptiveRoutingBenchmark",
    "default_scenario",
]
