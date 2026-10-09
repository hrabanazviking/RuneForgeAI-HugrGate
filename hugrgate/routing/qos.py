"""Quality-of-service classes. Slice 063.

QoS is the request's *posture*: how much of the ladder may be spent on
it. :class:`QoSClass` names the four postures; :func:`qos_profile`
returns the :class:`QoSProfile` that planners and executors consult:

- **depth_cap** — max rungs a synthesized ladder may hold;
- **weights** — (capability, latency, cost) blend for rung ordering;
- **parallel_width** — max speculative fan-out (slice 064);
- **hedge_allowed** / **hedge_delay_ms** — hedged inference (slice 065);
- **fast_path_probability** — early-exit bar (slice 066);
- **early_exit_delta** — stop when marginal gain falls below this.

This module unifies the ``QOS_DEPTH_CAPS``/``QOS_WEIGHTS`` tables slice
053 introduced — they now live here as the single source of truth, and
``synthesis.py`` imports them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

__all__ = [
    "QoSClass",
    "QoSProfile",
    "QOS_PROFILES",
    "qos_profile",
]


class QoSClass(str, Enum):
    BEST_EFFORT = "best_effort"
    STANDARD = "standard"
    PRIORITY = "priority"
    CRITICAL = "critical"

    @classmethod
    def parse(cls, name: str) -> "QoSClass":
        try:
            return cls(name)
        except ValueError:
            raise ValueError(
                f"unknown QoS class: {name!r}; expected one of "
                f"{[c.value for c in cls]}")


@dataclass(frozen=True)
class QoSProfile:
    """The routing posture for one QoS class."""

    name: QoSClass
    depth_cap: int
    weights: Tuple[float, float, float]  # capability, latency, cost
    parallel_width: int
    hedge_allowed: bool
    hedge_delay_ms: float
    fast_path_probability: float
    early_exit_delta: float

    def __post_init__(self):
        if self.depth_cap < 1:
            raise ValueError("depth_cap must be >= 1")
        if abs(sum(self.weights) - 1.0) > 1e-9:
            raise ValueError("weights must sum to 1.0")
        if self.parallel_width < 1:
            raise ValueError("parallel_width must be >= 1")
        if self.hedge_delay_ms < 0:
            raise ValueError("hedge_delay_ms must be non-negative")
        if not 0.0 <= self.fast_path_probability <= 1.0:
            raise ValueError("fast_path_probability must be in [0,1]")


QOS_PROFILES: Dict[QoSClass, QoSProfile] = {
    QoSClass.BEST_EFFORT: QoSProfile(
        name=QoSClass.BEST_EFFORT, depth_cap=2, weights=(0.2, 0.4, 0.4),
        parallel_width=1, hedge_allowed=False, hedge_delay_ms=100.0,
        fast_path_probability=0.90, early_exit_delta=0.05),
    QoSClass.STANDARD: QoSProfile(
        name=QoSClass.STANDARD, depth_cap=4, weights=(0.4, 0.3, 0.3),
        parallel_width=2, hedge_allowed=False, hedge_delay_ms=50.0,
        fast_path_probability=0.95, early_exit_delta=0.03),
    QoSClass.PRIORITY: QoSProfile(
        name=QoSClass.PRIORITY, depth_cap=6, weights=(0.6, 0.25, 0.15),
        parallel_width=3, hedge_allowed=True, hedge_delay_ms=50.0,
        fast_path_probability=0.97, early_exit_delta=0.02),
    QoSClass.CRITICAL: QoSProfile(
        name=QoSClass.CRITICAL, depth_cap=8, weights=(0.8, 0.15, 0.05),
        parallel_width=4, hedge_allowed=True, hedge_delay_ms=25.0,
        fast_path_probability=0.99, early_exit_delta=0.01),
}


def qos_profile(name: str) -> QoSProfile:
    """The profile for a QoS class name (as carried by RoutingOptions.qos)."""
    return QOS_PROFILES[QoSClass.parse(name)]
