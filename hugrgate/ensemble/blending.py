"""Blending engine — convex member weights from holdout data. Slice 108.

Blending is stacking's leaner sibling: instead of training a full
meta-learner, it learns one convex weight vector
(``wᵢ ≥ 0``, ``Σw = 1``) minimizing multiclass log-loss on a holdout
set of member predictions. Optimization is projected gradient descent
onto the probability simplex — uniform init, fixed iterations, fully
deterministic, pure Python.

When to reach for which:
- **blending**: few holdout samples, want an interpretable weight per
  member, hard to overfit;
- **stacking** (107): plenty of data, want per-class meta-weights
  (can anti-learn a member for one class while trusting it for
  another).

:class:`Blender` owns the fit/blend cycle; the ``"blending"``
combiner needs a fitted blender in ``ctx.fitted``.
"""

from __future__ import annotations

import math

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
    "Blender",
    "blending_combine",
    "log_loss",
    "project_simplex",
]

#: Floor for blended probabilities inside a log.
BLEND_EPS = 1e-12


def project_simplex(v: list[float]) -> list[float]:
    """Euclidean projection of ``v`` onto the probability simplex."""
    n = len(v)
    if n == 0:
        raise PolicyError("project_simplex needs a non-empty vector")
    order = sorted(v, reverse=True)
    cssv = 0.0
    rho = 0
    for j, u in enumerate(order):
        cssv += u
        if u + (1.0 - cssv) / (j + 1) > 0:
            rho = j
    theta = (sum(order[: rho + 1]) - 1.0) / (rho + 1)
    return [max(x - theta, 0.0) for x in v]


def log_loss(blended: dict[str, float], true_label: str) -> float:
    """Multiclass log-loss of one blended distribution."""
    return -math.log(max(blended.get(true_label, 0.0), BLEND_EPS))


class Blender:
    """Learns convex member weights on holdout predictions."""

    def __init__(self, members: list[str], lr: float = 0.5,
                 iters: int = 500):
        if not members:
            raise PolicyError("Blender needs at least one member")
        if len(set(members)) != len(members):
            raise PolicyError(
                f"member names must be unique, got {members}")
        if lr <= 0:
            raise PolicyError(f"lr must be > 0, got {lr}")
        if iters < 1:
            raise PolicyError(f"iters must be >= 1, got {iters}")
        self.members = list(members)
        self.lr = lr
        self.iters = iters
        self.classes: list[str] = []
        self._weights: list[float] = []
        self.holdout_log_loss: float = math.inf

    @property
    def fitted(self) -> bool:
        return bool(self._weights)

    @property
    def weights(self) -> dict[str, float]:
        if not self.fitted:
            raise BackendError("Blender used before fit")
        return dict(zip(self.members, self._weights, strict=True))

    def _matrix(self, votes_per_sample: list[list[MemberVote]],
                space: list[str]) -> list[list[list[float]]]:
        """Per-sample, per-member, per-class probability tensor."""
        tensor: list[list[list[float]]] = []
        for votes in votes_per_sample:
            by_member = {v.backend: v for v in votes if not v.skipped}
            rows = []
            for m in self.members:
                vote = by_member.get(m)
                if vote is None:
                    rows.append([0.0] * len(space))
                else:
                    dist = complete_distribution(vote, space)
                    rows.append([dist.get(o, 0.0) for o in space])
            tensor.append(rows)
        return tensor

    def fit(self, votes_per_sample: list[list[MemberVote]],
            labels: list[str], spec: DecisionSpec) -> Blender:
        """Learn the convex weight vector on holdout predictions."""
        require_discrete_spec(spec, "blending")
        if len(votes_per_sample) != len(labels):
            raise PolicyError(
                f"{len(votes_per_sample)} vote sets but "
                f"{len(labels)} labels")
        if not labels:
            raise PolicyError("Blender.fit needs labeled samples")
        space = spec.value_space()
        unknown = [label for label in labels if label not in space]
        if unknown:
            raise PolicyError(
                f"labels outside the spec space: {sorted(set(unknown))}")
        tensor = self._matrix(votes_per_sample, space)
        truth_idx = [space.index(label) for label in labels]
        m = len(self.members)
        w = [1.0 / m] * m  # uniform init: deterministic
        n = len(labels)
        for _ in range(self.iters):
            grad = [0.0] * m
            for rows, t in zip(tensor, truth_idx, strict=True):
                blended_t = sum(w[i] * rows[i][t] for i in range(m))
                denom = max(blended_t, BLEND_EPS)
                for i in range(m):
                    grad[i] += -rows[i][t] / denom
            w = project_simplex(
                [w[i] - self.lr * grad[i] / n for i in range(m)])
        self._weights = w
        self.classes = list(space)
        self.holdout_log_loss = sum(
            log_loss(
                {c: sum(w[i] * rows[i][k]
                        for i in range(m))
                 for k, c in enumerate(space)},
                labels[s])
            for s, rows in enumerate(tensor)) / n
        return self

    def blend(self, votes: list[MemberVote],
              spec: DecisionSpec) -> dict[str, float]:
        if not self.fitted:
            raise BackendError("Blender used before fit")
        space = spec.value_space()
        if space != self.classes:
            raise BackendError(
                f"spec space {space} differs from the fitted classes "
                f"{self.classes}")
        by_member = {v.backend: v for v in votes if not v.skipped}
        blended = {c: 0.0 for c in space}
        for i, name in enumerate(self.members):
            vote = by_member.get(name)
            if vote is None:
                continue
            dist = complete_distribution(vote, space)
            for c in space:
                blended[c] += self._weights[i] * dist.get(c, 0.0)
        return blended

    def to_dict(self) -> dict[str, object]:
        return {
            "members": list(self.members),
            "classes": list(self.classes),
            "fitted": self.fitted,
            "weights": self.weights if self.fitted else {},
            "holdout_log_loss": self.holdout_log_loss,
        }


def blending_combine(votes: list[MemberVote],
                     ctx: StrategyContext) -> DecisionResult:
    """Combine votes with the fitted blender's convex weights."""
    require_discrete_spec(ctx.spec, "blending")
    blender = ctx.fitted
    if not isinstance(blender, Blender) or not blender.fitted:
        raise BackendError(
            "blending strategy needs a fitted Blender "
            "(fit one, then Ensemble.attach(...)); got "
            f"{type(blender).__name__}")
    usable = [v for v in votes if not v.skipped]
    if not usable:
        raise BackendError("blending: no usable votes")
    distribution = blender.blend(votes, ctx.spec)
    first_seen: dict[str, int] = {}
    for i, v in enumerate(usable):
        if v.value is not None and str(v.value) not in first_seen:
            first_seen[str(v.value)] = i
    peak = max(distribution.values())
    tied = [k for k, p in distribution.items() if p == peak]
    winner = break_tie(tied, distribution, first_seen)
    return finalize_result(
        strategy="blending",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in usable},
        value=winner,
        probability=distribution[winner],
        distribution=distribution,
        uncertainty=normalized_entropy(distribution),
        winner_share=distribution[winner],
        extra={"blend_weights": blender.weights,
               "holdout_log_loss": blender.holdout_log_loss},
        model="ensemble:blending",
    )
