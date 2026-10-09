"""Safe exploration. Slice 142.

Slice 141 decides *when* to explore; this module decides *where it is
safe to*. :class:`SafeExploration` guarantees the exploration arm is
drawn only from candidates the application's policy already permits:

- :meth:`eligible` filters :class:`~hugrgate.adaptive.cost_quality.RoutingCandidate`
  arms through ``DecisionPolicy.backend_allowed`` (allowed-list, remote
  flag), the latency budget, the cost budget, and the strict-privacy
  gate (no remote, no data retention). The advisory ``privacy_ok`` flag
  is not consulted — same rule as slice 135.
- :meth:`choose` takes an ``exploit_arm`` (the incumbent best) and, when
  exploration is warranted, returns a *different* eligible arm uniformly
  at random — never the exploit arm (re-pulling the incumbent is not
  exploration), never an ineligible one.
- When no arm is eligible, it raises
  :class:`~hugrgate.errors.BackendUnavailable` instead of gambling:
  failing closed beats exploring blind.

The safety invariant is structural, not advisory: there is no code path
in :meth:`choose` that can return an ineligible arm, so tests can assert
it by construction rather than by sampling luck.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.adaptive.cost_quality import RoutingCandidate
from hugrgate.adaptive.exploration import ExplorationControls
from hugrgate.errors import BackendUnavailable, SpecError
from hugrgate.policy import DecisionPolicy

__all__ = [
    "SafeChoice",
    "SafeExploration",
]


@dataclass(frozen=True)
class SafeChoice:
    """One safe routing choice."""

    arm: str
    explored: bool
    eligible_arms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "explored": self.explored,
            "eligible_arms": list(self.eligible_arms),
        }


class SafeExploration:
    """Exploration confined to policy-permitted arms."""

    def __init__(self, controls: ExplorationControls,
                 seed: int | None = None) -> None:
        if not isinstance(controls, ExplorationControls):
            raise SpecError(
                "SafeExploration needs ExplorationControls, got "
                f"{type(controls).__name__}")
        self.controls = controls
        self._rng = random.Random(seed)

    def eligible(self, candidates: Sequence[RoutingCandidate],
                 policy: DecisionPolicy) -> list[RoutingCandidate]:
        """Candidates the policy permits — the only explorable set."""
        if not isinstance(policy, DecisionPolicy):
            raise SpecError(
                f"expected DecisionPolicy, got {type(policy).__name__}")
        eligible = []
        for cand in candidates:
            if not policy.backend_allowed(cand.name, cand.is_remote):
                continue
            if (policy.maximum_latency_ms is not None
                    and cand.latency_ms > policy.maximum_latency_ms):
                continue
            if policy.max_cost is not None and cand.cost > policy.max_cost:
                continue
            if policy.privacy_class == "strict":
                if cand.is_remote or cand.data_retained:
                    continue
            eligible.append(cand)
        return eligible

    def require_eligible(self, candidates: Sequence[RoutingCandidate],
                         policy: DecisionPolicy) -> list[RoutingCandidate]:
        eligible = self.eligible(candidates, policy)
        if not eligible:
            raise BackendUnavailable(
                "no routing candidate is eligible under the policy: safe "
                "exploration refuses to gamble")
        return eligible

    def choose(self, candidates: Sequence[RoutingCandidate],
               policy: DecisionPolicy,
               exploit_arm: str,
               arm_pulls: Mapping[str, int]) -> SafeChoice:
        """Pick the exploit arm, or — when warranted — a safe explore arm.

        ``exploit_arm`` must itself be eligible; an incumbent that the
        policy no longer permits is not a safe default.
        """
        eligible = self.require_eligible(candidates, policy)
        eligible_names = [c.name for c in eligible]
        if exploit_arm not in eligible_names:
            raise SpecError(
                f"exploit arm {exploit_arm!r} is not policy-eligible; "
                f"eligible: {eligible_names}")
        explore = self.controls.should_explore(
            {name: arm_pulls.get(name, 0) for name in eligible_names})
        if explore:
            alternatives = [n for n in eligible_names if n != exploit_arm]
            if alternatives:
                chosen = self._rng.choice(sorted(alternatives))
                self.controls.record_exploration()
                return SafeChoice(arm=chosen, explored=True,
                                  eligible_arms=eligible_names)
        self.controls.record_exploitation()
        return SafeChoice(arm=exploit_arm, explored=False,
                          eligible_arms=eligible_names)
