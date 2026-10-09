"""Exploration controls. Slice 141.

Learning requires trying arms that are not currently the best — but
unbounded exploration in production is how routers cause incidents.
:class:`ExplorationControls` is the throttle between the bandit's
curiosity and the operator's nerves:

- **Epsilon schedule.** ``epsilon`` decays geometrically per decision
  toward ``epsilon_min``: explore eagerly while young, exploit when
  seasoned.
- **Under-pulled priority.** Arms with fewer than ``min_pulls_per_arm``
  observations are always exploration-eligible, so no arm starves.
- **Budget cap.** Exploration never exceeds ``max_exploration_share``
  of recent decisions — a hard ceiling on how much traffic curiosity
  may spend.
- **Kill switch.** :meth:`disable` stops all exploration immediately
  (and :meth:`enable` resumes); the state is explicit and auditable, not
  a comment in a config file.

Deterministic given a seeded :class:`random.Random`: the same seed and
history produce the same explore/exploit sequence, which keeps tests
and replays honest.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SpecError

__all__ = [
    "ExplorationConfig",
    "ExplorationControls",
]


@dataclass(frozen=True)
class ExplorationConfig:
    """Knobs for the exploration throttle."""

    epsilon: float = 0.1
    epsilon_min: float = 0.01
    decay: float = 0.9995
    min_pulls_per_arm: int = 5
    max_exploration_share: float = 0.25
    enabled: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.epsilon <= 1.0:
            raise SpecError(f"epsilon must be in [0,1], got {self.epsilon}")
        if not 0.0 <= self.epsilon_min <= 1.0:
            raise SpecError(
                f"epsilon_min must be in [0,1], got {self.epsilon_min}")
        if self.epsilon_min > self.epsilon:
            raise SpecError("epsilon_min cannot exceed epsilon")
        if not 0.0 < self.decay <= 1.0:
            raise SpecError(f"decay must be in (0,1], got {self.decay}")
        if self.min_pulls_per_arm < 0:
            raise SpecError("min_pulls_per_arm must be >= 0")
        if not 0.0 <= self.max_exploration_share <= 1.0:
            raise SpecError(
                "max_exploration_share must be in [0,1], got "
                f"{self.max_exploration_share}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "epsilon": self.epsilon,
            "epsilon_min": self.epsilon_min,
            "decay": self.decay,
            "min_pulls_per_arm": self.min_pulls_per_arm,
            "max_exploration_share": self.max_exploration_share,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExplorationConfig:
        return cls(
            epsilon=float(data.get("epsilon", 0.1)),
            epsilon_min=float(data.get("epsilon_min", 0.01)),
            decay=float(data.get("decay", 0.9995)),
            min_pulls_per_arm=int(data.get("min_pulls_per_arm", 5)),
            max_exploration_share=float(
                data.get("max_exploration_share", 0.25)),
            enabled=bool(data.get("enabled", True)),
        )


class ExplorationControls:
    """Stateful epsilon-greedy throttle with budget and kill switch."""

    def __init__(self, config: ExplorationConfig | None = None,
                 seed: int | None = None) -> None:
        self.config = config or ExplorationConfig()
        self._rng = random.Random(seed)
        self._epsilon = self.config.epsilon
        self.decisions = 0
        self.explorations = 0
        self._enabled = self.config.enabled

    # -- state ----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def epsilon(self) -> float:
        return self._epsilon

    def disable(self) -> None:
        """Kill switch: stop all exploration immediately."""
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def step(self) -> None:
        """Advance one decision: count it and decay epsilon."""
        self.decisions += 1
        self._epsilon = max(self.config.epsilon_min,
                            self._epsilon * self.config.decay)

    # -- decisions ------------------------------------------------------

    def exploration_share(self) -> float:
        if self.decisions == 0:
            return 0.0
        return self.explorations / self.decisions

    def _over_budget(self) -> bool:
        return (self.exploration_share()
                >= self.config.max_exploration_share)

    def should_explore(self, arm_pulls: Mapping[str, int],
                       total_decisions: int | None = None) -> bool:
        """Decide whether this decision should explore.

        ``arm_pulls`` maps arm name -> times pulled. Exploration happens
        when enabled, under budget, and (a uniform draw < epsilon or any
        arm is under-pulled).
        """
        if not self._enabled:
            return False
        if self._over_budget():
            return False
        under_pulled = any(
            pulls < self.config.min_pulls_per_arm
            for pulls in arm_pulls.values())
        if under_pulled:
            return True
        return self._rng.random() < self._epsilon

    def record_exploration(self) -> None:
        self.explorations += 1
        self.step()

    def record_exploitation(self) -> None:
        self.step()

    def snapshot(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "enabled": self._enabled,
            "epsilon": self._epsilon,
            "decisions": self.decisions,
            "explorations": self.explorations,
            "exploration_share": self.exploration_share(),
        }
