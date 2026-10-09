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
    "HardwareAwarePlanner",
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
    "PrivacyAwarePlanner",
    "PrivacyTier",
    "BackendClearance",
    "DataClassifier",
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
    "RungMode",
    "RungNode",
    "RungPlanner",
    "RouterContext",
    "RoutingDecision",
    "RoutingOptions",
    "RoutingPlan",
    "SerialPlanExecutor",
    "score_capability",
]
