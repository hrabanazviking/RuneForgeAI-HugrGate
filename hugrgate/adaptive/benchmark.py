"""Adaptive routing benchmark. Slice 149.

Claims about adaptive routing need a reproducible arena, not anecdotes.
:class:`AdaptiveRoutingBenchmark` replays a synthetic-but-deterministic
contextual scenario for ``rounds`` rounds and compares four policies:

- ``uniform`` - random arm each round (the "no learning" floor);
- ``round_robin`` - deterministic rotation (the naive-fair baseline);
- ``static_first`` - always the first arm (the "don't bother" baseline);
- ``adaptive`` - the LinUCB :class:`~hugrgate.adaptive.bandit.ContextualBanditAdapter`
  (slice 130) learning online from observed rewards.

The scenario is a callable ``(rng, round_idx) -> (features, rewards)``
returning the context features and the *true* per-arm rewards for that
round; a default context-dependent scenario is provided
(:func:`default_scenario`) where the best arm depends on the context, so
a learning policy can genuinely beat the static baselines.

:func:`run` returns a :class:`BenchmarkArtifact` - every number computed
from the replay, with the baselines' mean rewards stated explicitly so
"adaptive beats X" is checkable, never asserted. :meth:`save` writes it
as JSON; the checked-in artifact at
``docs/campaign-vi/artifacts/adaptive-routing-benchmark.json`` is
regenerated at full rounds after the test suite runs (tests use reduced
rounds for speed).
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hugrgate.adaptive.bandit import ContextualBanditAdapter
from hugrgate.errors import SpecError

__all__ = [
    "POLICIES",
    "AdaptiveRoutingBenchmark",
    "BenchmarkArtifact",
    "Scenario",
    "default_scenario",
]

#: Policies compared by the benchmark.
POLICIES = ("uniform", "round_robin", "static_first", "adaptive")

#: ``(rng, round_idx) -> (features, {arm: true_reward})``.
Scenario = Callable[[random.Random, int],
                    tuple[dict[str, float], dict[str, float]]]

ARMS = ("arm_a", "arm_b", "arm_c")
FEATURE_NAMES = ("x0", "x1", "bias")


def default_scenario(rng: random.Random, round_idx: int
                     ) -> tuple[dict[str, float], dict[str, float]]:
    """Context-dependent rewards: the best arm depends on ``x0``.

    - ``arm_a`` is excellent when ``x0 > 0.5``, poor otherwise;
    - ``arm_b`` is the mirror image;
    - ``arm_c`` is a constant mediocre fallback.

    An optimal contextual policy earns 0.9 every round; uniform random
    earns ~0.583. Gaussian noise (sigma=0.05, clipped) keeps it honest.
    """
    del round_idx  # the scenario is stationary in time
    x0 = rng.random()
    x1 = rng.random()
    base = {
        "arm_a": 0.9 if x0 > 0.5 else 0.3,
        "arm_b": 0.9 if x0 <= 0.5 else 0.3,
        "arm_c": 0.55,
    }
    rewards = {arm: min(1.0, max(0.0, mu + rng.gauss(0.0, 0.05)))
               for arm, mu in base.items()}
    return ({"x0": x0, "x1": x1, "bias": 1.0}, rewards)


@dataclass(frozen=True)
class BenchmarkArtifact:
    """Every number the benchmark computed, nothing invented."""

    generated_at: float
    rounds: int
    seed: int
    policies: tuple[str, ...]
    mean_reward: dict[str, float]
    total_reward: dict[str, float]
    pulls: dict[str, dict[str, int]]
    winner: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "rounds": self.rounds,
            "seed": self.seed,
            "policies": list(self.policies),
            "mean_reward": dict(self.mean_reward),
            "total_reward": dict(self.total_reward),
            "pulls": {p: dict(c) for p, c in self.pulls.items()},
            "winner": self.winner,
            "config": dict(self.config),
        }

    def summary(self) -> str:
        lines = [f"adaptive-routing benchmark: {self.rounds} rounds, "
                 f"seed {self.seed}"]
        for policy in self.policies:
            lines.append(f"  {policy:12s} mean_reward="
                         f"{self.mean_reward[policy]:.4f} "
                         f"total={self.total_reward[policy]:.1f}")
        lines.append(f"winner: {self.winner}")
        return "\n".join(lines)


class AdaptiveRoutingBenchmark:
    """Replay a scenario; compare adaptive routing against baselines."""

    def __init__(self, *, rounds: int = 2000, seed: int = 7,
                 alpha: float = 1.0, ridge: float = 1.0) -> None:
        if rounds < 1:
            raise SpecError(f"rounds must be >= 1, got {rounds}")
        if alpha < 0:
            raise SpecError(f"alpha must be >= 0, got {alpha}")
        if ridge <= 0:
            raise SpecError(f"ridge must be > 0, got {ridge}")
        self.rounds = rounds
        self.seed = seed
        self.alpha = alpha
        self.ridge = ridge

    def run(self, scenario: Scenario = default_scenario,
            arms: tuple[str, ...] = ARMS) -> BenchmarkArtifact:
        """Replay ``rounds`` rounds; return the measured artifact."""
        if not arms:
            raise SpecError("benchmark needs at least one arm")
        rng = random.Random(self.seed)
        bandit = ContextualBanditAdapter(
            FEATURE_NAMES, alpha=self.alpha, ridge=self.ridge)
        totals = {p: 0.0 for p in POLICIES}
        pulls: dict[str, dict[str, int]] = {
            p: {a: 0 for a in arms} for p in POLICIES}
        for round_idx in range(self.rounds):
            features, rewards = scenario(rng, round_idx)
            if set(rewards) != set(arms):
                raise SpecError(
                    f"scenario rewards {sorted(rewards)} do not match arms "
                    f"{sorted(arms)}")
            choices = {
                "uniform": rng.choice(list(arms)),
                "round_robin": arms[round_idx % len(arms)],
                "static_first": arms[0],
                "adaptive": bandit.select(features, list(arms)).arm,
            }
            for policy, arm in choices.items():
                totals[policy] += rewards[arm]
                pulls[policy][arm] += 1
            # The adaptive policy learns from what it actually pulled.
            bandit.update(choices["adaptive"], features,
                          rewards[choices["adaptive"]])
        mean_reward = {p: totals[p] / self.rounds for p in POLICIES}
        winner = max(POLICIES, key=lambda p: (mean_reward[p], p))
        return BenchmarkArtifact(
            generated_at=time.time(),
            rounds=self.rounds,
            seed=self.seed,
            policies=POLICIES,
            mean_reward=mean_reward,
            total_reward=dict(totals),
            pulls=pulls,
            winner=winner,
            config={"alpha": self.alpha, "ridge": self.ridge,
                    "scenario": getattr(scenario, "__name__", "custom"),
                    "arms": list(arms)},
        )

    def save(self, artifact: BenchmarkArtifact, path: str) -> str:
        """Write the artifact as pretty JSON. Returns the path."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(artifact.to_dict(), fh, indent=2, sort_keys=True)
            fh.write("\n")
        return path

    @staticmethod
    def load(path: str) -> dict[str, Any]:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
