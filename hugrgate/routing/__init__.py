"""Ladder II — intelligence routing subsystem (Campaign III).

A plan/execute-separated routing architecture built on top of the v1
:class:`~hugrgate.ladder.LadderRouter`. Each Campaign III slice adds one
module to this package; the package docstring of each module names its
slice.
"""

from hugrgate.routing.architecture import (
    LadderRouterV2,
    RungExecutor,
    RungMode,
    RungNode,
    RungPlanner,
    RouterContext,
    RoutingDecision,
    RoutingOptions,
    RoutingPlan,
    SerialPlanExecutor,
)
from hugrgate.routing.capability import (
    CapabilityScore,
    CapabilityScorer,
    WEIGHTS as CAPABILITY_WEIGHTS,
)
from hugrgate.routing.availability import (
    AvailabilityAwarePlanner,
    AvailabilityTracker,
    CircuitState,
)
from hugrgate.routing.confidence import (
    CalibrationTracker,
    ConfidenceAwarePlanner,
    adjusted_gate,
)
from hugrgate.routing.dag import (
    DAGExecutor,
    DAGNode,
    RoutingDAG,
    evaluate_condition,
)
from hugrgate.routing.dsl import (
    RoutePolicy,
    parse as parse_route_policy,
)
from hugrgate.routing.explain import (
    OUTCOME_PHRASES,
    explain_decision,
    explain_plan,
    explain_route,
)
from hugrgate.routing.fuzz import (
    FuzzBackend,
    run_fuzz,
)
from hugrgate.routing.replay import (
    RecordingExecutor,
    ReplayExecutor,
    RouteRecording,
    replay,
)
from hugrgate.routing.simulate import (
    SimulatedRung,
    SimulationReport,
    simulate,
)
from hugrgate.routing.cost import (
    CostAwarePlanner,
    CostLedger,
    budget_for,
)
from hugrgate.routing.energy import (
    DEFAULT_LOCAL_WATTS,
    DEFAULT_REMOTE_WATTS,
    EnergyAwarePlanner,
    EnergyLedger,
    EnergyModel,
)
from hugrgate.routing.hardware import (
    HardwareAwarePlanner,
    HostProfile,
    hardware_compatible,
)
from hugrgate.routing.early_exit import (
    EarlyExitExecutor,
)
from hugrgate.routing.fallback import (
    FallbackGraph,
    FallbackGraphExecutor,
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
from hugrgate.routing.qos import (
    QOS_PROFILES,
    QoSClass,
    QoSProfile,
    qos_profile,
)
from hugrgate.routing.privacy import (
    BackendClearance,
    DataClassifier,
    PrivacyAwarePlanner,
    PrivacyTier,
)
from hugrgate.routing.rungs import (
    DynamicRungPlanner,
    RungBuilder,
    RungFilter,
)
from hugrgate.routing.synthesis import (
    QOS_DEPTH_CAPS,
    QOS_WEIGHTS,
    LadderSynthesizer,
    score_capability,
)

__all__ = [
    "CAPABILITY_WEIGHTS",
    "AvailabilityAwarePlanner",
    "AvailabilityTracker",
    "CalibrationTracker",
    "CircuitState",
    "CapabilityScore",
    "CapabilityScorer",
    "ConfidenceAwarePlanner",
    "CostAwarePlanner",
    "CostLedger",
    "DEFAULT_LOCAL_WATTS",
    "DEFAULT_REMOTE_WATTS",
    "DynamicRungPlanner",
    "EnergyAwarePlanner",
    "EnergyLedger",
    "EnergyModel",
    "OUTCOME_PHRASES",
    "explain_decision",
    "explain_plan",
    "explain_route",
    "EarlyExitExecutor",
    "FallbackGraph",
    "FuzzBackend",
    "FallbackGraphExecutor",
    "HardwareAwarePlanner",
    "HedgedPlanExecutor",
    "HostProfile",
    "adjusted_gate",
    "budget_for",
    "hardware_compatible",
    "LadderRouterV2",
    "LadderSynthesizer",
    "LatencyAwarePlanner",
    "LatencyTracker",
    "MemoryAwarePlanner",
    "MemoryModel",
    "ParallelPlanExecutor",
    "PrivacyAwarePlanner",
    "PrivacyTier",
    "BackendClearance",
    "DAGExecutor",
    "DAGNode",
    "DataClassifier",
    "RoutingDAG",
    "evaluate_condition",
    "QOS_PROFILES",
    "QoSClass",
    "QoSProfile",
    "qos_profile",
    "DEFAULT_LOCAL_MEMORY_MB",
    "DEFAULT_REMOTE_MEMORY_MB",
    "QOS_DEPTH_CAPS",
    "QOS_WEIGHTS",
    "RungBuilder",
    "RungExecutor",
    "RungFilter",
    "RecordingExecutor",
    "ReplayExecutor",
    "RouteRecording",
    "RungMode",
    "replay",
    "RungNode",
    "RungPlanner",
    "RouterContext",
    "RoutingDecision",
    "RoutingOptions",
    "RoutePolicy",
    "RoutingPlan",
    "run_fuzz",
    "parse_route_policy",
    "SerialPlanExecutor",
    "SimulatedRung",
    "SimulationReport",
    "simulate",
    "score_capability",
]
