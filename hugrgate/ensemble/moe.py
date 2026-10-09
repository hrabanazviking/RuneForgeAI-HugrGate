"""Mixture-of-experts router — route by input region. Slice 109.

Every other strategy asks the same members about every input. A
mixture of experts instead *routes*: a gating network maps the input
state to a distribution over experts, the top-k experts are consulted,
and their ballots are combined with the gate weights.

Training (supervised, deterministic): for each labeled sample, the
target gate distribution is uniform over the experts that voted
correctly (uniform over all when none did — the sample teaches no
preference). The gating network is softmax regression on the state
features, trained with batch gradient descent from zero init —
soft targets, so it is implemented here rather than reusing the
hard-label regression from :mod:`hugrgate.ensemble.stacking`.

:class:`ExpertRouter` owns features/fit/routing; the ``"moe"``
combiner needs a fitted router in ``ctx.fitted`` **and** the input
state in ``ctx.state`` (wired by :meth:`Ensemble.evaluate`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from hugrgate.ensemble.base import (
    MemberVote,
    StrategyContext,
    break_tie,
    complete_distribution,
    finalize_result,
    normalized_entropy,
    require_discrete_spec,
)
from hugrgate.errors import BackendError, PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "ExpertRouter",
    "moe_combine",
]


def _softmax(logits: list[float]) -> list[float]:
    peak = max(logits)
    exps = [math.exp(logit - peak) for logit in logits]
    total = sum(exps)
    return [e / total for e in exps]


class ExpertRouter:
    """Gating network routing states to experts."""

    def __init__(self, members: list[str], feature_names: list[str],
                 top_k: int | None = None,
                 l2: float = 0.01, lr: float = 1.0,
                 iters: int = 1000):
        if not members:
            raise PolicyError("ExpertRouter needs at least one member")
        if len(set(members)) != len(members):
            raise PolicyError(
                f"member names must be unique, got {members}")
        if not feature_names:
            raise PolicyError("ExpertRouter needs at least one feature")
        if top_k is not None and (top_k < 1 or top_k > len(members)):
            raise PolicyError(
                f"top_k must be in [1, {len(members)}], got {top_k}")
        if l2 < 0:
            raise PolicyError(f"l2 must be >= 0, got {l2}")
        if lr <= 0:
            raise PolicyError(f"lr must be > 0, got {lr}")
        if iters < 1:
            raise PolicyError(f"iters must be >= 1, got {iters}")
        self.members = list(members)
        self.feature_names = list(feature_names)
        self.top_k = top_k if top_k is not None else len(members)
        self.l2 = l2
        self.lr = lr
        self.iters = iters
        self.classes: list[str] = []
        self._w: list[list[float]] = []  # [feature][member]
        self._b: list[float] = []

    @property
    def fitted(self) -> bool:
        return bool(self._w)

    def extract(self, state: Mapping[str, Any]) -> list[float]:
        """Numeric feature vector; missing/non-numeric → 0.0."""
        feats = []
        for name in self.feature_names:
            raw = state.get(name, 0.0)
            feats.append(float(raw) if isinstance(raw, (int, float))
                         and math.isfinite(raw) else 0.0)
        return feats

    def _gates(self, x: list[float]) -> list[float]:
        logits = [
            sum(x[j] * self._w[j][i] for j in range(len(x))) + self._b[i]
            for i in range(len(self.members))
        ]
        return _softmax(logits)

    def fit(self, states: list[Mapping[str, Any]],
            votes_per_sample: list[list[MemberVote]],
            labels: list[str], spec: DecisionSpec) -> ExpertRouter:
        """Train the gating network.

        The target for each sample is uniform over the experts that
        voted the true label (uniform over all when none did).
        """
        require_discrete_spec(spec, "moe")
        n = len(labels)
        if not (len(states) == len(votes_per_sample) == n):
            raise PolicyError(
                f"states/votes/labels lengths disagree: {len(states)}, "
                f"{len(votes_per_sample)}, {n}")
        if n == 0:
            raise PolicyError("ExpertRouter.fit needs labeled samples")
        space = spec.value_space()
        unknown = [label for label in labels if label not in space]
        if unknown:
            raise PolicyError(
                f"labels outside the spec space: {sorted(set(unknown))}")
        X = [self.extract(s) for s in states]
        m = len(self.members)
        d = len(self.feature_names)
        # Soft targets: uniform over the experts that were right.
        targets: list[list[float]] = []
        for votes, label in zip(votes_per_sample, labels, strict=True):
            by_member = {v.backend: v for v in votes if not v.skipped}
            correct = [i for i, name in enumerate(self.members)
                       if name in by_member
                       and by_member[name].value == label]
            if not correct:
                correct = list(range(m))
            t = [0.0] * m
            for i in correct:
                t[i] = 1.0 / len(correct)
            targets.append(t)
        w = [[0.0] * m for _ in range(d)]
        b = [0.0] * m
        for _ in range(self.iters):
            gw = [[0.0] * m for _ in range(d)]
            gb = [0.0] * m
            for x, t in zip(X, targets, strict=True):
                logits = [sum(x[j] * w[j][i] for j in range(d)) + b[i]
                          for i in range(m)]
                probs = _softmax(logits)
                for i in range(m):
                    err = probs[i] - t[i]
                    gb[i] += err
                    for j in range(d):
                        gw[j][i] += err * x[j]
            for j in range(d):
                for i in range(m):
                    w[j][i] -= self.lr * (gw[j][i] / n + self.l2 * w[j][i])
            for i in range(m):
                b[i] -= self.lr * gb[i] / n
        self._w, self._b = w, b
        self.classes = list(space)
        return self

    def route(self, state: Mapping[str, Any],
              candidates: list[str] | None = None) -> dict[str, float]:
        """Gate distribution over (optionally restricted) members."""
        if not self.fitted:
            raise BackendError("ExpertRouter used before fit")
        names = [c for c in self.members
                 if candidates is None or c in candidates]
        if not names:
            raise BackendError("ExpertRouter.route: no candidates")
        gates = self._gates(self.extract(state))
        return {name: gates[self.members.index(name)] for name in names}

    def route_topk(self, state: Mapping[str, Any], k: int | None = None,
                   candidates: list[str] | None = None
                   ) -> dict[str, float]:
        """Top-k gates, renormalized to sum to 1."""
        gates = self.route(state, candidates)
        k = self.top_k if k is None else k
        if k < 1:
            raise PolicyError(f"top_k must be >= 1, got {k}")
        top = sorted(gates, key=lambda n: (-gates[n], n))[:k]
        total = sum(gates[n] for n in top)
        if total <= 0:
            raise BackendError("ExpertRouter: top-k gates sum to zero")
        return {n: gates[n] / total for n in top}

    def to_dict(self) -> dict[str, object]:
        return {
            "members": list(self.members),
            "feature_names": list(self.feature_names),
            "top_k": self.top_k,
            "fitted": self.fitted,
            "classes": list(self.classes),
        }


def moe_combine(votes: list[MemberVote],
                ctx: StrategyContext) -> DecisionResult:
    """Route the input state to the top-k experts and combine."""
    require_discrete_spec(ctx.spec, "moe")
    router = ctx.fitted
    if not isinstance(router, ExpertRouter) or not router.fitted:
        raise BackendError(
            "moe strategy needs a fitted ExpertRouter "
            "(fit one, then Ensemble.attach(...)); got "
            f"{type(router).__name__}")
    if ctx.state is None:
        raise BackendError(
            "moe strategy needs the input state for routing "
            "(ctx.state is None)")
    usable = [v for v in votes if not v.skipped]
    if not usable:
        raise BackendError("moe: no usable votes")
    k = ctx.options.get("top_k", router.top_k)
    gates = router.route_topk(ctx.state, k,
                              [v.backend for v in usable])
    by_member = {v.backend: v for v in usable}
    space = ctx.spec.value_space()
    averaged: dict[str, float] = {}
    for name, gate in gates.items():
        for key, p in complete_distribution(by_member[name],
                                            space).items():
            averaged[key] = averaged.get(key, 0.0) + gate * p
    first_seen: dict[str, int] = {}
    for i, v in enumerate(usable):
        if v.value is not None and str(v.value) not in first_seen:
            first_seen[str(v.value)] = i
    peak = max(averaged.values())
    tied = [k2 for k2, p in averaged.items() if p == peak]
    winner = break_tie(tied, averaged, first_seen)
    return finalize_result(
        strategy="moe",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in usable},
        value=winner,
        probability=averaged[winner],
        distribution=averaged,
        uncertainty=normalized_entropy(averaged),
        winner_share=averaged[winner],
        extra={"gates": gates,
               "routed_experts": sorted(gates),
               "top_k": k},
        model="ensemble:moe",
    )
