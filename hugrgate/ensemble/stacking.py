"""Stacking engine — a meta-learner over member predictions. Slice 107.

Stacking trains a second-level model on the members' out-of-fold
predictions instead of fixing combination weights up front. The
meta-learner here is multinomial logistic regression (softmax)
implemented in pure Python — zero-init batch gradient descent, fixed
iteration count, fully deterministic, no scikit-learn dependency:

- meta-features: each member's (completed) probability vector over
  the spec's value space, concatenated;
- target: the true label;
- L2-regularized cross-entropy, bias unregularized.

:class:`StackingEngine` owns the feature layout and the fitted
regression; the ``"stacking"`` combiner needs a fitted engine in
``ctx.fitted`` (via ``Ensemble.attach``).
"""

from __future__ import annotations

import math
from typing import Dict, List

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
    "SoftmaxRegression",
    "StackingEngine",
    "stacking_combine",
]


def _softmax(logits: List[float]) -> List[float]:
    peak = max(logits)
    exps = [math.exp(l - peak) for l in logits]
    total = sum(exps)
    return [e / total for e in exps]


class SoftmaxRegression:
    """Multinomial logistic regression, deterministic by construction."""

    def __init__(self, n_features: int, n_classes: int,
                 l2: float = 0.01, lr: float = 1.0,
                 iters: int = 1000):
        if n_features < 1 or n_classes < 2:
            raise PolicyError(
                "SoftmaxRegression needs >=1 feature and >=2 classes, "
                f"got {n_features} features, {n_classes} classes")
        if l2 < 0:
            raise PolicyError(f"l2 must be >= 0, got {l2}")
        if lr <= 0:
            raise PolicyError(f"lr must be > 0, got {lr}")
        if iters < 1:
            raise PolicyError(f"iters must be >= 1, got {iters}")
        self.n_features = n_features
        self.n_classes = n_classes
        self.l2 = l2
        self.lr = lr
        self.iters = iters
        # Zero init: the entire fit is a deterministic function of data.
        self.weights: List[List[float]] = [
            [0.0] * n_classes for _ in range(n_features)]
        self.bias: List[float] = [0.0] * n_classes
        self._fitted = False

    @property
    def fitted(self) -> bool:
        return self._fitted

    def _logits(self, x: List[float]) -> List[float]:
        return [
            sum(x[j] * self.weights[j][k] for j in range(self.n_features))
            + self.bias[k]
            for k in range(self.n_classes)
        ]

    def fit(self, X: List[List[float]],
            y: List[int]) -> "SoftmaxRegression":
        n = len(X)
        if n == 0:
            raise PolicyError("SoftmaxRegression.fit needs data")
        if len(y) != n:
            raise PolicyError(
                f"X has {n} rows but y has {len(y)} labels")
        for i, row in enumerate(X):
            if len(row) != self.n_features:
                raise PolicyError(
                    f"row {i} has {len(row)} features, expected "
                    f"{self.n_features}")
            if not 0 <= y[i] < self.n_classes:
                raise PolicyError(
                    f"label {y[i]} out of range for "
                    f"{self.n_classes} classes")
        for _ in range(self.iters):
            grad_w = [[0.0] * self.n_classes
                      for _ in range(self.n_features)]
            grad_b = [0.0] * self.n_classes
            for row, label in zip(X, y):
                probs = _softmax(self._logits(row))
                for k in range(self.n_classes):
                    err = probs[k] - (1.0 if k == label else 0.0)
                    grad_b[k] += err
                    for j in range(self.n_features):
                        grad_w[j][k] += err * row[j]
            for j in range(self.n_features):
                for k in range(self.n_classes):
                    grad = grad_w[j][k] / n + self.l2 * self.weights[j][k]
                    self.weights[j][k] -= self.lr * grad
            for k in range(self.n_classes):
                self.bias[k] -= self.lr * grad_b[k] / n
        self._fitted = True
        return self

    def predict_proba(self, x: List[float]) -> List[float]:
        if not self._fitted:
            raise BackendError(
                "SoftmaxRegression used before fit")
        if len(x) != self.n_features:
            raise PolicyError(
                f"expected {self.n_features} features, got {len(x)}")
        return _softmax(self._logits(x))

    def predict(self, x: List[float]) -> int:
        probs = self.predict_proba(x)
        return max(range(len(probs)), key=lambda k: probs[k])


class StackingEngine:
    """Meta-learner over member prediction vectors."""

    def __init__(self, members: List[str],
                 l2: float = 0.01, lr: float = 1.0,
                 iters: int = 1000):
        if not members:
            raise PolicyError("StackingEngine needs at least one member")
        if len(set(members)) != len(members):
            raise PolicyError(
                f"member names must be unique, got {members}")
        self.members = list(members)
        self.l2 = l2
        self.lr = lr
        self.iters = iters
        self.classes: List[str] = []
        self.regression: SoftmaxRegression | None = None

    @property
    def fitted(self) -> bool:
        return self.regression is not None and self.regression.fitted

    def _features(self, votes: List[MemberVote],
                  space: List[str]) -> List[float]:
        by_member = {v.backend: v for v in votes if not v.skipped}
        feats: List[float] = []
        for name in self.members:
            vote = by_member.get(name)
            if vote is None:
                feats.extend([0.0] * len(space))
            else:
                dist = complete_distribution(vote, space)
                feats.extend(dist.get(o, 0.0) for o in space)
        return feats

    def fit(self, votes_per_sample: List[List[MemberVote]],
            labels: List[str], spec: DecisionSpec) -> "StackingEngine":
        """Train the meta-learner.

        ``votes_per_sample[i]`` holds every member's vote on sample
        ``i``; ``labels[i]`` is the true label.
        """
        require_discrete_spec(spec, "stacking")
        if len(votes_per_sample) != len(labels):
            raise PolicyError(
                f"{len(votes_per_sample)} vote sets but "
                f"{len(labels)} labels")
        if not labels:
            raise PolicyError("StackingEngine.fit needs labeled samples")
        space = spec.value_space()
        unknown = [l for l in labels if l not in space]
        if unknown:
            raise PolicyError(
                f"labels outside the spec space: {sorted(set(unknown))}")
        X = [self._features(votes, space) for votes in votes_per_sample]
        y = [space.index(l) for l in labels]
        self.classes = list(space)
        self.regression = SoftmaxRegression(
            len(self.members) * len(space), len(space),
            l2=self.l2, lr=self.lr, iters=self.iters)
        self.regression.fit(X, y)
        return self

    def predict_proba(self, votes: List[MemberVote],
                      spec: DecisionSpec) -> Dict[str, float]:
        if not self.fitted or self.regression is None:
            raise BackendError("StackingEngine used before fit")
        space = spec.value_space()
        if space != self.classes:
            raise BackendError(
                f"spec space {space} differs from the fitted classes "
                f"{self.classes}")
        probs = self.regression.predict_proba(
            self._features(votes, space))
        return {c: p for c, p in zip(self.classes, probs)}

    def to_dict(self) -> Dict[str, object]:
        return {
            "members": list(self.members),
            "classes": list(self.classes),
            "fitted": self.fitted,
            "l2": self.l2,
            "lr": self.lr,
            "iters": self.iters,
        }


def stacking_combine(votes: List[MemberVote],
                     ctx: StrategyContext) -> DecisionResult:
    """Combine votes through the fitted stacking meta-learner."""
    require_discrete_spec(ctx.spec, "stacking")
    engine = ctx.fitted
    if not isinstance(engine, StackingEngine) or not engine.fitted:
        raise BackendError(
            "stacking strategy needs a fitted StackingEngine "
            "(fit one, then Ensemble.attach(...)); got "
            f"{type(engine).__name__}")
    usable = [v for v in votes if not v.skipped]
    if not usable:
        raise BackendError("stacking: no usable votes")
    distribution = engine.predict_proba(votes, ctx.spec)
    first_seen: Dict[str, int] = {}
    for i, v in enumerate(usable):
        if v.value is not None and str(v.value) not in first_seen:
            first_seen[str(v.value)] = i
    peak = max(distribution.values())
    tied = [k for k, p in distribution.items() if p == peak]
    winner = break_tie(tied, distribution, first_seen)
    return finalize_result(
        strategy="stacking",
        spec=ctx.spec,
        votes=votes,
        weights={v.backend: v.weight for v in usable},
        value=winner,
        probability=distribution[winner],
        distribution=distribution,
        uncertainty=normalized_entropy(distribution),
        winner_share=distribution[winner],
        extra={"meta_classes": list(distribution)},
        model="ensemble:stacking",
    )
