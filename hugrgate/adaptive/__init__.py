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

from hugrgate.adaptive.bandit import (
    BanditDecision,
    ContextualBanditAdapter,
)
from hugrgate.adaptive.benchmark import (
    POLICIES as BENCHMARK_POLICIES,
)
from hugrgate.adaptive.benchmark import (
    AdaptiveRoutingBenchmark,
    BenchmarkArtifact,
    default_scenario,
)
from hugrgate.adaptive.coldstart import (
    ColdStartRouting,
)
from hugrgate.adaptive.competence import (
    BackendCompetenceProfiles,
    CompetenceProfile,
    wilson_lower_bound,
)
from hugrgate.adaptive.contract_competence import (
    PerContractCompetence,
    contract_of_event,
    contract_of_spec,
)
from hugrgate.adaptive.cost_quality import (
    CostQualityObjective,
    RouteObjective,
    RoutingCandidate,
)
from hugrgate.adaptive.counterfactual import (
    ESTIMATORS as COUNTERFACTUAL_ESTIMATORS,
)
from hugrgate.adaptive.counterfactual import (
    CounterfactualEvaluator,
    PolicyValueEstimate,
)
from hugrgate.adaptive.delayed import (
    DelayedLabel,
    DelayedLabelIngestion,
    SweepReport,
)
from hugrgate.adaptive.domain_competence import (
    UNKNOWN_DOMAIN,
    PerDomainCompetence,
    domain_of_event,
    domain_of_spec,
)
from hugrgate.adaptive.drift_detect import (
    AdaptiveDriftReport,
    AdaptiveRouteDriftDetector,
)
from hugrgate.adaptive.energy_quality import (
    DEFAULT_LOCAL_WATTS,
    DEFAULT_REMOTE_WATTS,
    EnergyMeasurement,
    EnergyQualityObjective,
    estimate_energy_wh,
    measure_energy,
)
from hugrgate.adaptive.explanations import (
    AdaptiveRouteExplainer,
    FeatureContribution,
    RouteExplanation,
)
from hugrgate.adaptive.exploration import (
    ExplorationConfig,
    ExplorationControls,
)
from hugrgate.adaptive.feedback import (
    OUTCOME_LABELS,
    OutcomeFeedbackAPI,
    OutcomeRecord,
)
from hugrgate.adaptive.latency_quality import (
    LatencyMeasurement,
    LatencyQualityObjective,
    compare_to_baseline,
    measure_latency,
)
from hugrgate.adaptive.multiobjective import (
    MODES as MULTIOBJECTIVE_MODES,
)
from hugrgate.adaptive.multiobjective import (
    MultiObjectiveRouter,
    dominates,
    pareto_frontier,
)
from hugrgate.adaptive.offline import (
    LearningDiagnostics,
    OfflinePolicyLearning,
)
from hugrgate.adaptive.privacy_objective import (
    PrivacyConstrainedObjective,
)
from hugrgate.adaptive.rollback import (
    Checkpoint,
    RouterRollback,
)
from hugrgate.adaptive.router_features import (
    SPEC_TYPES as ROUTER_SPEC_TYPES,
)
from hugrgate.adaptive.router_features import (
    RouteContext,
    RouterFeatureExtractor,
)
from hugrgate.adaptive.safe_exploration import (
    SafeChoice,
    SafeExploration,
)
from hugrgate.adaptive.shadow import (
    RouterShadowMode,
    ShadowDivergence,
)
from hugrgate.adaptive.telemetry import (
    SCHEMA_VERSION as TELEMETRY_SCHEMA_VERSION,
)
from hugrgate.adaptive.telemetry import (
    RouteEvent,
    TelemetryStore,
)
from hugrgate.adaptive.versioning import (
    AdaptivePolicyVersioning,
    PolicyVersion,
    digest_state,
)

__all__ = [
    "BENCHMARK_POLICIES",
    "COUNTERFACTUAL_ESTIMATORS",
    "DEFAULT_LOCAL_WATTS",
    "DEFAULT_REMOTE_WATTS",
    "MULTIOBJECTIVE_MODES",
    "OUTCOME_LABELS",
    "ROUTER_SPEC_TYPES",
    "TELEMETRY_SCHEMA_VERSION",
    "UNKNOWN_DOMAIN",
    "AdaptiveDriftReport",
    "AdaptivePolicyVersioning",
    "AdaptiveRouteDriftDetector",
    "AdaptiveRouteExplainer",
    "AdaptiveRoutingBenchmark",
    "BackendCompetenceProfiles",
    "BanditDecision",
    "BenchmarkArtifact",
    "Checkpoint",
    "ColdStartRouting",
    "CompetenceProfile",
    "ContextualBanditAdapter",
    "CostQualityObjective",
    "CounterfactualEvaluator",
    "DelayedLabel",
    "DelayedLabelIngestion",
    "EnergyMeasurement",
    "EnergyQualityObjective",
    "ExplorationConfig",
    "ExplorationControls",
    "FeatureContribution",
    "LatencyMeasurement",
    "LatencyQualityObjective",
    "LearningDiagnostics",
    "MultiObjectiveRouter",
    "OfflinePolicyLearning",
    "OutcomeFeedbackAPI",
    "OutcomeRecord",
    "PerContractCompetence",
    "PerDomainCompetence",
    "PolicyValueEstimate",
    "PolicyVersion",
    "PrivacyConstrainedObjective",
    "RouteContext",
    "RouteEvent",
    "RouteExplanation",
    "RouteObjective",
    "RouterFeatureExtractor",
    "RouterRollback",
    "RouterShadowMode",
    "RoutingCandidate",
    "SafeChoice",
    "SafeExploration",
    "ShadowDivergence",
    "SweepReport",
    "TelemetryStore",
    "compare_to_baseline",
    "contract_of_event",
    "contract_of_spec",
    "default_scenario",
    "digest_state",
    "domain_of_event",
    "domain_of_spec",
    "dominates",
    "estimate_energy_wh",
    "measure_energy",
    "measure_latency",
    "pareto_frontier",
    "wilson_lower_bound",
]
