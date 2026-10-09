"""Ensemble-weight tuner. Slice 460.

Attacks a real weakness: :class:`hugrgate.ensemble.blending.Blender`
learns weights online with a fixed learning rate, and ensemble
weights elsewhere are hand-set. This tuner finds the batch-optimal
weights on labeled data.

Setup: K members, N samples, C classes. Member m gives a probability
vector p[n][m][c]; the blend is ``sum_m w_m · p[n][m]`` with w on the
simplex. Objective: mean log-likelihood of the true labels.

Optimization: projected gradient ascent on the simplex (reusing
:func:`hugrgate.ensemble.blending.project_simplex` — no duplication),
with backtracking line search (Armijo) and a deterministic uniform
start. The gradient is exact:

    dL/dw_m = mean_n p[n][m][y_n] / blend[n][y_n].

The tuner proposes one float param per member
(``{weight_prefix}.{member}`` in [0, 1]); consumers normalize. A
proposal requires the tuned log-likelihood to beat the current
(store) weights — normalized to the simplex — by ``min_delta``.

Evidence carries baseline/tuned weights and log-likelihoods plus the
iteration count, so the win is re-derivable from the input votes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.autotune.controller import Proposal, TuningContext
from hugrgate.autotune.tuners._base import BaseTuner
from hugrgate.ensemble.blending import BLEND_EPS, project_simplex
from hugrgate.errors import TunerError

__all__ = ["EnsembleWeightTuner", "mean_log_likelihood"]


def mean_log_likelihood(votes: Sequence[Sequence[Sequence[float]]],
                        labels: Sequence[int],
                        weights: Sequence[float]) -> float:
    """Mean log-likelihood of the simplex-weighted blend."""
    total = 0.0
    for probs_per_member, y in zip(votes, labels, strict=True):
        blend = sum(w * probs_per_member[m][y]
                    for m, w in enumerate(weights))
        total += math.log(max(blend, BLEND_EPS))
    return total / len(votes)


@dataclass
class EnsembleWeightTuner(BaseTuner):
    """Batch-optimal ensemble weights via projected gradient ascent."""

    name: str = "ensemble_weight_tuner"
    members: Sequence[str] = field(default_factory=list)
    votes: Sequence[Sequence[Sequence[float]]] = field(default_factory=list)
    labels: Sequence[int] = field(default_factory=list)
    weight_prefix: str = "ensemble.weight"
    max_iter: int = 200
    tol: float = 1e-6

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise TunerError("weight tuner needs an objective_id")
        if len(self.members) < 2:
            raise TunerError("need at least 2 members")
        if len(set(self.members)) != len(self.members):
            raise TunerError("duplicate member names")
        if not self.votes or len(self.votes) != len(self.labels):
            raise TunerError("votes and labels must be non-empty and aligned")
        n_classes = len(self.votes[0][0])
        for n, (probs, y) in enumerate(zip(self.votes, self.labels,
                                           strict=True)):
            if len(probs) != len(self.members):
                raise TunerError("vote/member count mismatch", sample=n)
            if not 0 <= y < n_classes:
                raise TunerError("label out of range", sample=n)
            for _m, dist in enumerate(probs):
                if len(dist) != n_classes:
                    raise TunerError("class count mismatch", sample=n)
                if any((not isinstance(p, (int, float))
                        or p < 0 or not math.isfinite(p)) for p in dist):
                    raise TunerError("probabilities must be finite >= 0",
                                     sample=n)
                if sum(dist) <= 0:
                    raise TunerError("member distribution sums to 0",
                                     sample=n)
        if not self.weight_prefix:
            raise TunerError("weight_prefix must be non-empty")

    def _param(self, member: str) -> str:
        return f"{self.weight_prefix}.{member}"

    def _gradient(self, weights: Sequence[float]) -> list[float]:
        k = len(self.members)
        grads = [0.0] * k
        for probs_per_member, y in zip(self.votes, self.labels,
                                       strict=True):
            blend = max(sum(w * probs_per_member[m][y]
                            for m, w in enumerate(weights)), BLEND_EPS)
            for m in range(k):
                grads[m] += probs_per_member[m][y] / blend
        return [g / len(self.votes) for g in grads]

    def _optimize(self) -> tuple[list[float], float, int]:
        k = len(self.members)
        w = [1.0 / k] * k
        cur = mean_log_likelihood(self.votes, self.labels, w)
        iters = 0
        for it in range(1, self.max_iter + 1):
            iters = it
            grad = self._gradient(w)
            step = 1.0
            prev = list(w)
            for _ in range(40):  # backtracking line search
                cand = project_simplex(
                    [wi + step * gi for wi, gi in zip(w, grad, strict=True)])
                val = mean_log_likelihood(self.votes, self.labels, cand)
                if val > cur + 1e-12:
                    w, cur = cand, val
                    break
                step *= 0.5
            else:
                break  # no improving step: stationary
            if max(abs(a - b) for a, b in zip(w, prev, strict=True)) \
                    < self.tol:
                break
        return w, cur, iters

    def tune(self, ctx: TuningContext) -> Proposal | None:
        for m in self.members:
            param = ctx.store.describe(self._param(m))
            if param.dtype != "float":
                raise TunerError("weight params must be float",
                                 param=self._param(m))
        tuned, tuned_ll, iters = self._optimize()
        raw = [float(ctx.store.get(self._param(m))) for m in self.members]
        s = sum(raw)
        base_w = [r / s if s > 0 else 1.0 / len(raw) for r in raw]
        base_ll = mean_log_likelihood(self.votes, self.labels, base_w)
        changes = {self._param(m): w for m, w in zip(self.members, tuned,
                                                     strict=True)}
        evidence: dict[str, Any] = {
            "members": list(self.members),
            "n_samples": len(self.votes),
            "iterations": iters,
            "baseline": {"weights": dict(zip(self.members, base_w,
                                             strict=True)),
                         "mean_log_likelihood": base_ll},
            "tuned": {"weights": dict(zip(self.members, tuned,
                                           strict=True)),
                      "mean_log_likelihood": tuned_ll},
        }
        return self._propose(ctx, changes, base_ll, tuned_ll, evidence)
