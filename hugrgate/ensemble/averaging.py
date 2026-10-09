"""Bayesian model averaging adapter. Slice 106.

Adapts HugrGate backends — which emit :class:`DecisionResult`s, not
Bayesian evidences — into Bayesian model averaging terms:

``P(Mᵢ|D) ∝ P(D|Mᵢ) · P(Mᵢ)``

- the **prior** ``P(Mᵢ)`` is operator-supplied (uniform by default);
- the **evidence** ``P(D|Mᵢ)`` is estimated from predictive
  log-likelihoods: each labeled outcome contributes
  ``log Pᵢ(true label)`` to the member's accumulated log-evidence.

:meth:`BayesianModelAverager.posterior_weights` turns the accumulated
evidence into the posterior model probabilities; the ``"bma"``
combiner averages member distributions with those weights. Members
with no observations yet fall back to their prior — the adapter never
punishes a member for not having been scored.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

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

__all__ = [
    "LOG_EPS",
    "BayesianModelAverager",
    "bma_combine",
    "predictive_log_likelihood",
]

#: Floor for predictive probabilities inside a log: a member that put
#: zero mass on the truth gets a harsh but finite penalty, never -inf.
LOG_EPS = 1e-12


def predictive_log_likelihood(distribution: Mapping[str, float],
                              true_label: str) -> float:
    """``log P(true_label)`` under a member's predictive distribution."""
    p = max(float(distribution.get(true_label, 0.0)), LOG_EPS)
    return math.log(p)


class BayesianModelAverager:
    """Accumulates per-member evidence and reports posterior weights."""

    def __init__(self, members: list[str],
                 priors: Mapping[str, float] | None = None):
        if not members:
            raise PolicyError(
                "BayesianModelAverager needs at least one member")
        if len(set(members)) != len(members):
            raise PolicyError(
                f"member names must be unique, got {members}")
        self.members = list(members)
        if priors is None:
            self.priors = {m: 1.0 / len(members) for m in members}
        else:
            unknown = [k for k in priors if k not in members]
            if unknown:
                raise PolicyError(
                    f"priors name unknown member(s): {unknown}")
            for m in members:
                p = priors.get(m, 0.0)
                if not isinstance(p, (int, float)) or not math.isfinite(p):
                    raise PolicyError(
                        f"prior for {m!r} must be finite, got {p!r}")
                if p < 0:
                    raise PolicyError(
                        f"prior for {m!r} must be >= 0, got {p}")
            total = sum(priors.get(m, 0.0) for m in members)
            if total <= 0:
                raise PolicyError("priors must sum to a positive value")
            self.priors = {m: priors.get(m, 0.0) / total
                           for m in members}
        self._log_evidence: dict[str, float] = {m: 0.0 for m in members}
        self._observations: dict[str, int] = {m: 0 for m in members}

    def observe(self, member: str, log_likelihood: float) -> None:
        """Accumulate one predictive log-likelihood for ``member``."""
        if member not in self._log_evidence:
            raise PolicyError(
                f"unknown member {member!r}; members are {self.members}")
        if not isinstance(log_likelihood, (int, float)) or not math.isfinite(
                log_likelihood):
            raise PolicyError(
                f"log_likelihood must be finite, got {log_likelihood!r}")
        self._log_evidence[member] += float(log_likelihood)
        self._observations[member] += 1

    def observe_outcome(self, member: str,
                        distribution: Mapping[str, float],
                        true_label: str) -> float:
        """Score a labeled outcome; returns the log-likelihood added."""
        ll = predictive_log_likelihood(distribution, true_label)
        self.observe(member, ll)
        return ll

    @property
    def log_evidences(self) -> dict[str, float]:
        return dict(self._log_evidence)

    @property
    def observation_counts(self) -> dict[str, int]:
        return dict(self._observations)

    def posterior_weights(self) -> dict[str, float]:
        """Softmax over ``log(prior) + log_evidence`` (numerically stable)."""
        log_post = [math.log(max(self.priors[m], LOG_EPS))
                    + self._log_evidence[m] for m in self.members]
        peak = max(log_post)
        exps = [math.exp(lp - peak) for lp in log_post]
        total = sum(exps)
        return {m: e / total for m, e in zip(self.members, exps, strict=True)}

    def to_dict(self) -> dict[str, object]:
        return {
            "members": list(self.members),
            "priors": dict(self.priors),
            "log_evidences": dict(self._log_evidence),
            "observations": dict(self._observations),
            "posterior_weights": self.posterior_weights(),
        }


def bma_combine(votes: list[MemberVote],
                ctx: StrategyContext) -> DecisionResult:
    """Average member distributions with BMA posterior weights.

    The fitted :class:`BayesianModelAverager` rides in
    ``ctx.fitted`` (attached via ``Ensemble.attach``); without one the
    combiner refuses with a helpful error rather than guessing.
    """
    require_discrete_spec(ctx.spec, "bma")
    averager = ctx.fitted
    if not isinstance(averager, BayesianModelAverager):
        raise BackendError(
            "bma strategy needs a fitted BayesianModelAverager "
            "(attach one via Ensemble.attach(...)); got "
            f"{type(averager).__name__}")
    usable = [v for v in votes if not v.skipped]
    if not usable:
        raise BackendError("bma: no usable votes")
    space = ctx.spec.value_space()
    posterior = averager.posterior_weights()
    # Renormalize the posterior over the members that actually voted:
    # mass assigned to silent members must not leak out of the average.
    voted_mass = sum(posterior.get(v.backend, 0.0) for v in usable)
    if voted_mass <= 0:
        raise BackendError("bma: voting members carry no posterior mass")
    weights = {v.backend: posterior.get(v.backend, 0.0) / voted_mass
               for v in usable}
    averaged: dict[str, float] = {}
    for v in usable:
        w = weights[v.backend]
        for key, p in complete_distribution(v, space).items():
            averaged[key] = averaged.get(key, 0.0) + w * p
    if not averaged:
        raise BackendError("bma: posterior weights are all zero")
    first_seen: dict[str, int] = {}
    for i, v in enumerate(usable):
        if v.value is not None and str(v.value) not in first_seen:
            first_seen[str(v.value)] = i
    peak = max(averaged.values())
    tied = [k for k, p in averaged.items() if p == peak]
    winner = break_tie(tied, averaged, first_seen)
    return finalize_result(
        strategy="bma",
        spec=ctx.spec,
        votes=votes,
        weights=weights,
        value=winner,
        probability=averaged[winner],
        distribution=averaged,
        uncertainty=normalized_entropy(averaged),
        winner_share=averaged[winner],
        extra={"posterior_weights": posterior,
               "log_evidences": averager.log_evidences,
               "observation_counts": averager.observation_counts},
        model="ensemble:bma",
    )
