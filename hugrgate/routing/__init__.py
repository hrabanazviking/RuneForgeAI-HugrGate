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
from hugrgate.routing.rungs import (
    DynamicRungPlanner,
    RungBuilder,
    RungFilter,
)

__all__ = [
    "DynamicRungPlanner",
    "LadderRouterV2",
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
]
