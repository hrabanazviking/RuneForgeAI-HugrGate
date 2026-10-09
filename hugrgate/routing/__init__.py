"""Ladder II — intelligence routing subsystem (Campaign III).

A plan/execute-separated routing architecture built on top of the v1
:class:`~hugrgate.ladder.LadderRouter`. Each Campaign III slice adds one
module to this package; the package docstring of each module names its
slice.
"""

from hugrgate.routing.architecture import (
    LadderRouterV2,
    RouterContext,
    RoutingDecision,
    RoutingOptions,
    RoutingPlan,
    RungExecutor,
    RungMode,
    RungNode,
    RungPlanner,
    SerialPlanExecutor,
)
from hugrgate.routing.availability import (
    AvailabilityAwarePlanner,
    AvailabilityTracker,
    CircuitState,
)
from hugrgate.routing.capability import (
    WEIGHTS as CAPABILITY_WEIGHTS,
)
from hugrgate.routing.capability import (
    CapabilityScore,
    CapabilityScorer,
)
from hugrgate.routing.confidence import (
    CalibrationTracker,
    ConfidenceAwarePlanner,
    adjusted_gate,
)
from hugrgate.routing.cost import (
    CostAwarePlanner,
    CostLedger,
    budget_for,
)
from hugrgate.routing.dag import (
    DAGExecutor,
    DAGNode,
    RoutingDAG,
    evaluate_condition,
)
from hugrgate.routing.dsl import (
    RoutePolicy,
)
from hugrgate.routing.dsl import (
    parse as parse_route_policy,
)
from hugrgate.routing.early_exit import (
    EarlyExitExecutor,
)
from hugrgate.routing.energy import (
    DEFAULT_LOCAL_WATTS,
    DEFAULT_REMOTE_WATTS,
    EnergyAwarePlanner,
    EnergyLedger,
    EnergyModel,
)
from hugrgate.routing.explain import (
    OUTCOME_PHRASES,
    explain_decision,
    explain_plan,
    explain_route,
)
from hugrgate.routing.fallback import (
    FallbackGraph,
    FallbackGraphExecutor,
)
from hugrgate.routing.fuzz import (
    FuzzBackend,
    run_fuzz,
)
from hugrgate.routing.hardware import (
    HardwareAwarePlanner,
    HostProfile,
    hardware_compatible,
)
from hugrgate.routing.hedged import (
    HedgedPlanExecutor,
)
from hugrgate.routing.latency import (
    LatencyAwarePlanner,
    LatencyTracker,
)
from hugrgate.routing.memory import (
    DEFAULT_LOCAL_MEMORY_MB,
    DEFAULT_REMOTE_MEMORY_MB,
    MemoryAwarePlanner,
    MemoryModel,
)
from hugrgate.routing.parallel import (
    ParallelPlanExecutor,
)
from hugrgate.routing.privacy import (
    BackendClearance,
    DataClassifier,
    PrivacyAwarePlanner,
    PrivacyTier,
)
from hugrgate.routing.qos import (
    QOS_PROFILES,
    QoSClass,
    QoSProfile,
    qos_profile,
)
from hugrgate.routing.replay import (
    RecordingExecutor,
    ReplayExecutor,
    RouteRecording,
    replay,
)
from hugrgate.routing.rungs import (
    DynamicRungPlanner,
    RungBuilder,
    RungFilter,
)
from hugrgate.routing.simulate import (
    SimulatedRung,
    SimulationReport,
    simulate,
)
from hugrgate.routing.synthesis import (
    QOS_DEPTH_CAPS,
    QOS_WEIGHTS,
    LadderSynthesizer,
    score_capability,
)

__all__ = [
    "CAPABILITY_WEIGHTS",
    "DEFAULT_LOCAL_MEMORY_MB",
    "DEFAULT_LOCAL_WATTS",
    "DEFAULT_REMOTE_MEMORY_MB",
    "DEFAULT_REMOTE_WATTS",
    "OUTCOME_PHRASES",
    "QOS_DEPTH_CAPS",
    "QOS_PROFILES",
    "QOS_WEIGHTS",
    "AvailabilityAwarePlanner",
    "AvailabilityTracker",
    "BackendClearance",
    "CalibrationTracker",
    "CapabilityScore",
    "CapabilityScorer",
    "CircuitState",
    "ConfidenceAwarePlanner",
    "CostAwarePlanner",
    "CostLedger",
    "DAGExecutor",
    "DAGNode",
    "DataClassifier",
    "DynamicRungPlanner",
    "EarlyExitExecutor",
    "EnergyAwarePlanner",
    "EnergyLedger",
    "EnergyModel",
    "FallbackGraph",
    "FallbackGraphExecutor",
    "FuzzBackend",
    "HardwareAwarePlanner",
    "HedgedPlanExecutor",
    "HostProfile",
    "LadderRouterV2",
    "LadderSynthesizer",
    "LatencyAwarePlanner",
    "LatencyTracker",
    "MemoryAwarePlanner",
    "MemoryModel",
    "ParallelPlanExecutor",
    "PrivacyAwarePlanner",
    "PrivacyTier",
    "QoSClass",
    "QoSProfile",
    "RecordingExecutor",
    "ReplayExecutor",
    "RoutePolicy",
    "RouteRecording",
    "RouterContext",
    "RoutingDAG",
    "RoutingDecision",
    "RoutingOptions",
    "RoutingPlan",
    "RungBuilder",
    "RungExecutor",
    "RungFilter",
    "RungMode",
    "RungNode",
    "RungPlanner",
    "SerialPlanExecutor",
    "SimulatedRung",
    "SimulationReport",
    "adjusted_gate",
    "budget_for",
    "evaluate_condition",
    "explain_decision",
    "explain_plan",
    "explain_route",
    "hardware_compatible",
    "parse_route_policy",
    "qos_profile",
    "replay",
    "run_fuzz",
    "score_capability",
    "simulate",
]
