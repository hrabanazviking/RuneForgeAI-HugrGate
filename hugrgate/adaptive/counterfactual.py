"""Counterfactual route evaluation. Slice 144.

"What would policy π have earned on the traffic we actually served?"
:class:`CounterfactualEvaluator` answers from logged telemetry —
``(features, candidates, chosen, propensity, reward)`` tuples — without
serving π to a single live request.

Estimators:

- ``"ips"`` — inverse propensity scoring: ``Σ (π(x)=a) · r / μ(a|x) / n``.
  Unbiased but high-variance when π and the logging policy μ disagree.
- ``"snips"`` — self-normalized IPS: divides by ``Σ 1/μ(a|x) / n``.
  Slightly biased, much calmer; the default.
- ``"dr"`` — doubly robust: IPS on the *residual* of a reward model
  plus the model's direct prediction. Unbiased if *either* the
  propensities or the reward model are right. The reward model here is
  a :class:`~hugrgate.adaptive.bandit.ContextualBanditAdapter` trained
  on the same log (or supplied by the caller).

Only labeled, non-shadow events with positive propensities participate;
everything skipped is counted in the report. The evaluator never invents
rewards: an event without a usable reward is excluded, not imputed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.adaptive.offline import OfflinePolicyLearning
from hugrgate.adaptive.telemetry import RouteEvent
from hugrgate.errors import SpecError

__all__ = [
    "ESTIMATORS",
    "CounterfactualEvaluator",
    "PolicyValueEstimate",
]

ESTIMATORS = ("ips", "snips", "dr")

#: target_policy(features, candidates) -> chosen arm name.
TargetPolicy = Callable[[dict[str, float], list[str]], str]


@dataclass(frozen=True)
class PolicyValueEstimate:
    """Estimated mean reward of the target policy on logged traffic."""

    estimator: str
    value: float
    n_events: int
    n_used: int
    n_skipped: int
    effective_sample_size: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimator": self.estimator,
            "value": self.value,
            "n_events": self.n_events,
            "n_used": self.n_used,
            "n_skipped": self.n_skipped,
            "effective_sample_size": self.effective_sample_size,
        }


class CounterfactualEvaluator:
    """Off-policy value estimation for candidate routing policies."""

    def __init__(self, feature_names: Sequence[str], *,
                 min_propensity: float = 1e-3,
                 max_weight: float = 100.0) -> None:
        if not 0.0 < min_propensity <= 1.0:
            raise SpecError(
                f"min_propensity must be in (0,1], got {min_propensity}")
        if max_weight <= 0:
            raise SpecError(f"max_weight must be positive, got {max_weight}")
        self.feature_names = list(feature_names)
        self.min_propensity = min_propensity
        self.max_weight = max_weight

    def _usable(self, events: Iterable[RouteEvent]
                ) -> list[RouteEvent]:
        usable = []
        for event in events:
            if event.shadow or not event.labeled:
                continue
            quality = event.quality
            if quality is None:
                continue
            if event.propensities.get(event.chosen, 0.0) \
                    < self.min_propensity:
                continue
            usable.append(event)
        return usable

    def _reward_model(self, events: list[RouteEvent]
                      ) -> ContextualBanditAdapter:
        learner = OfflinePolicyLearning(
            self.feature_names, min_propensity=self.min_propensity,
            max_weight=self.max_weight, min_events=1)
        return learner.fit(events)

    def estimate(self, events: Iterable[RouteEvent],
                 target_policy: TargetPolicy,
                 estimator: str = "snips",
                 reward_model: ContextualBanditAdapter | None = None
                 ) -> PolicyValueEstimate:
        """Estimate the target policy's mean reward on logged traffic."""
        if estimator not in ESTIMATORS:
            raise SpecError(
                f"unknown estimator {estimator!r}; expected one of "
                f"{list(ESTIMATORS)}")
        events = list(events)
        usable = self._usable(events)
        n_skipped = len(events) - len(usable)
        if not usable:
            raise SpecError(
                "counterfactual evaluation needs at least one usable "
                "(labeled, non-shadow, positive-propensity) event")
        model = None
        if estimator == "dr":
            model = reward_model or self._reward_model(usable)

        weighted_rewards: list[float] = []
        weights: list[float] = []
        dm_terms: list[float] = []
        for event in usable:
            target_arm = target_policy(dict(event.features),
                                       list(event.candidates))
            if target_arm not in event.candidates:
                raise SpecError(
                    f"target policy chose {target_arm!r}, not a logged "
                    f"candidate for event {event.request_id!r}")
            reward = event.quality
            # _usable() guarantees a non-None quality; assert for the
            # type checker rather than silently defaulting.
            assert reward is not None
            reward = float(reward)
            propensity = event.propensities[event.chosen]
            w = min(1.0 / propensity, self.max_weight)
            if target_arm == event.chosen:
                weighted_rewards.append(w * reward)
                weights.append(w)
                if model is not None:
                    pred = model.expected_reward(target_arm,
                                                 dict(event.features))
                    dm_terms.append(pred + w * (reward - pred))
            else:
                if model is not None:
                    pred = model.expected_reward(target_arm,
                                                 dict(event.features))
                    dm_terms.append(pred)
                # IPS/SNIPS: target didn't take the logged action →
                # contributes nothing to the numerator.

        if estimator == "dr":
            value = sum(dm_terms) / len(dm_terms)
        elif estimator == "ips":
            value = sum(weighted_rewards) / len(usable)
        else:  # snips
            denom = sum(weights)
            value = (sum(weighted_rewards) / denom) if denom > 0 else 0.0

        total_w = sum(weights)
        ess = (total_w * total_w / sum(w * w for w in weights)) \
            if weights else 0.0
        return PolicyValueEstimate(
            estimator=estimator,
            value=value,
            n_events=len(events),
            n_used=len(usable),
            n_skipped=n_skipped,
            effective_sample_size=ess,
        )
