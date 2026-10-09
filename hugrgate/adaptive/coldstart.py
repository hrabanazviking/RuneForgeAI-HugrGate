"""Cold-start routing. Slice 140.

A brand-new backend (or a new domain, contract, or deployment) has no
history, and "no history" must not mean "never tried" — nor "blindly
trusted". :class:`ColdStartRouting` gives newcomers a fair, conservative
start:

- **Shrinkage priors.** A backend with ``n`` observations gets its mean
  shrunk toward the fleet-wide global mean with strength
  ``prior_strength``: ``(n·mean + k·global) / (n + k)``. At ``n = 0``
  the prior *is* the estimate; as evidence accumulates, the backend's
  own record takes over.
- **Bandit seeding.** :meth:`seed_bandit` translates the shrunk prior
  into :meth:`~hugrgate.adaptive.bandit.ContextualBanditAdapter.seed_prior`
  calls, so LinUCB starts exploring from "average" rather than zero —
  zero would systematically under-explore newcomers when rewards are
  positive.
- **Prioritized maiden voyages.** :meth:`recommend` picks the arm with
  the best shrunk prior mean among arms with fewer than
  ``maiden_voyages`` observations, guaranteeing newcomers get their
  first real trials instead of starving behind incumbents.

The global prior is honest about ignorance: it is the fleet mean, not a
marketing number, and every shrinkage is auditable via
:meth:`prior_report`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.adaptive.competence import BackendCompetenceProfiles
from hugrgate.errors import SpecError

__all__ = [
    "ColdStartRouting",
]


class ColdStartRouting:
    """Conservative priors for backends with little or no history."""

    def __init__(self, profiles: BackendCompetenceProfiles, *,
                 prior_strength: float = 10.0,
                 maiden_voyages: int = 5) -> None:
        if not isinstance(profiles, BackendCompetenceProfiles):
            raise SpecError(
                "ColdStartRouting needs BackendCompetenceProfiles, got "
                f"{type(profiles).__name__}")
        if not (isinstance(prior_strength, (int, float))
                and prior_strength > 0):
            raise SpecError(
                f"prior_strength must be > 0, got {prior_strength}")
        if maiden_voyages < 1:
            raise SpecError(
                f"maiden_voyages must be >= 1, got {maiden_voyages}")
        self.profiles = profiles
        self.prior_strength = float(prior_strength)
        self.maiden_voyages = maiden_voyages

    # -- shrinkage ------------------------------------------------------

    def _fleet_mean(self, arms: Sequence[str]) -> float:
        total_q = 0.0
        total_n = 0
        for arm in arms:
            profile = self.profiles.get(arm)
            if profile is not None:
                total_q += profile.quality_sum
                total_n += profile.attempts
        if total_n == 0:
            return 0.5  # no evidence anywhere: neutral prior
        return total_q / total_n

    def shrunk_mean(self, arm: str, arms: Sequence[str]) -> float:
        """Prior-shrunk quality estimate for ``arm``."""
        fleet = self._fleet_mean(arms)
        profile = self.profiles.get(arm)
        n = profile.attempts if profile else 0
        own = profile.mean_quality if profile else fleet
        k = self.prior_strength
        return (n * own + k * fleet) / (n + k)

    def prior_report(self, arms: Sequence[str]) -> list[dict[str, Any]]:
        """Auditable shrinkage detail per arm."""
        fleet = self._fleet_mean(arms)
        report = []
        for arm in arms:
            profile = self.profiles.get(arm)
            n = profile.attempts if profile else 0
            report.append({
                "arm": arm,
                "attempts": n,
                "own_mean": profile.mean_quality if profile else None,
                "fleet_mean": fleet,
                "shrunk_mean": self.shrunk_mean(arm, arms),
                "is_cold": n < self.maiden_voyages,
            })
        return report

    # -- routing ----------------------------------------------------------

    def recommend(self, arms: Sequence[str]) -> str:
        """Best shrunk-mean arm, with newcomers first.

        Arms below ``maiden_voyages`` observations compete among
        themselves by shrunk mean; only when every arm has graduated do
        incumbents compete on the same basis. Ties break by arm name.
        """
        arm_list = list(arms)
        if not arm_list:
            raise SpecError("recommend needs at least one arm")

        def pulls(a: str) -> int:
            profile = self.profiles.get(a)
            return profile.attempts if profile is not None else 0

        cold = [a for a in arm_list if pulls(a) < self.maiden_voyages]
        pool = cold or arm_list
        scored = [(self.shrunk_mean(a, arm_list), a) for a in pool]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return scored[0][1]

    def seed_bandit(self, bandit: ContextualBanditAdapter,
                    arms: Sequence[str]) -> dict[str, float]:
        """Seed a bandit's priors from shrunk competence means.

        Returns the per-arm prior mean used, for auditability.
        """
        arm_list = list(arms)
        if not arm_list:
            raise SpecError("seed_bandit needs at least one arm")
        used: dict[str, float] = {}
        dim = bandit.dim
        for arm in arm_list:
            mean = self.shrunk_mean(arm, arm_list)
            # Prior concentrated on the bias-like first feature if one
            # exists; otherwise spread evenly — a neutral direction.
            vec = [mean / dim] * dim
            bandit.seed_prior(arm, vec, strength=self.prior_strength)
            used[arm] = mean
        return used

    def cold_arms(self, arms: Sequence[str]) -> list[str]:
        """Arms still below the maiden-voyage threshold."""
        out = []
        for arm in arms:
            profile = self.profiles.get(arm)
            n = profile.attempts if profile else 0
            if n < self.maiden_voyages:
                out.append(arm)
        return out
