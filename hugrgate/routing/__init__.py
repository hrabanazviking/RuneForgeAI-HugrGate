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
from hugrgate.routing.confidence import (
    CalibrationTracker,
    ConfidenceAwarePlanner,
    adjusted_gate,
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
    "CalibrationTracker",
    "CapabilityScore",
    "CapabilityScorer",
    "ConfidenceAwarePlanner",
    "DynamicRungPlanner",
    "adjusted_gate",
    "LadderRouterV2",
    "LadderSynthesizer",
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
