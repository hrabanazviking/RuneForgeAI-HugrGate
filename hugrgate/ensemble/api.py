"""Ensemble API — one decision from many backends. Slice 101.

:class:`Ensemble` is itself a :class:`~hugrgate.backend.Backend`, so it
plugs into :class:`~hugrgate.core.HugrGate`, the daemon, the HTTP
server, and the policy/provenance machinery with no special casing:
register it, and ``gate.decide(state, spec)`` fans out to every member
and combines their ballots with the chosen strategy.

Strategies live in a registry (:func:`register_strategy`) so new
combiners (voting variants, BMA, stacking, blending, mixture of
experts) plug in without touching this module. The built-in set:

- ``"soft"`` — average member distributions, elect the argmax
  (:mod:`hugrgate.ensemble.voting`)

``Ensemble`` also exposes :meth:`decide_batch` for the batch path
(slice 122 builds on it).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional

from hugrgate.backend import Backend
from hugrgate.ensemble.base import (
    Combiner,
    MemberVote,
    StrategyContext,
    collect_votes,
    normalize_weights,
)
from hugrgate.ensemble.voting import soft_voting
from hugrgate.errors import BackendError, PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result, validate_state

__all__ = [
    "STRATEGIES",
    "register_strategy",
    "get_strategy",
    "Ensemble",
    "EnsembleConfig",
]

#: strategy name -> combiner. Populated at import with the built-ins;
#: extended by later slices and by applications via register_strategy.
STRATEGIES: Dict[str, Combiner] = {}


def register_strategy(name: str, combiner: Combiner) -> None:
    """Register a named vote combiner.

    Raises :class:`PolicyError` for a blank name or a non-callable
    combiner; re-registering a name replaces it (documented, deliberate:
    applications may override built-ins).
    """
    if not isinstance(name, str) or not name.strip():
        raise PolicyError(
            f"strategy name must be a non-empty string, got {name!r}")
    if not callable(combiner):
        raise PolicyError(
            f"combiner for strategy {name!r} must be callable, "
            f"got {type(combiner).__name__}")
    STRATEGIES[name] = combiner


def get_strategy(name: str) -> Combiner:
    """Return the combiner registered under ``name``."""
    try:
        return STRATEGIES[name]
    except KeyError:
        raise BackendError(
            f"unknown ensemble strategy {name!r}; "
            f"registered: {sorted(STRATEGIES)}")


register_strategy("soft", soft_voting)


class EnsembleConfig:
    """Tunable knobs for :class:`Ensemble` (beyond strategy choice)."""

    def __init__(self,
                 weights: Optional[Mapping[str, float]] = None,
                 min_members: int = 1,
                 strategy_options: Optional[Dict[str, Any]] = None):
        if min_members < 1:
            raise PolicyError(
                f"min_members must be >= 1, got {min_members}")
        self.weights = dict(weights) if weights else None
        self.min_members = min_members
        self.strategy_options = dict(strategy_options) if strategy_options \
            else {}


class Ensemble(Backend):
    """A backend composed of member backends and a vote combiner.

    Usage::

        ensemble = Ensemble([rules_a, rules_b, logreg], strategy="soft")
        gate.register(ensemble)
        result = gate.decide(state, spec)
    """

    is_remote = False

    def __init__(self,
                 members: List[Backend],
                 strategy: str = "soft",
                 name: Optional[str] = None,
                 config: Optional[EnsembleConfig] = None,
                 weights: Optional[Mapping[str, float]] = None,
                 min_members: Optional[int] = None,
                 strategy_options: Optional[Dict[str, Any]] = None):
        if not members:
            raise PolicyError("Ensemble needs at least one member backend")
        for m in members:
            if not isinstance(m, Backend):
                raise PolicyError(
                    "Ensemble members must be Backend instances, got "
                    f"{type(m).__name__}")
        names = [m.name for m in members]
        if len(set(names)) != len(names):
            raise PolicyError(
                f"Ensemble member names must be unique, got {names}")
        get_strategy(strategy)  # fail fast on unknown strategy
        self.members = list(members)
        self.strategy = strategy
        self.name = name or f"ensemble[{strategy}]"
        if not self.name.strip():
            raise PolicyError("Ensemble name must be a non-empty string")
        # A config object carries the defaults; explicit kwargs override
        # it field by field (None = "not given").
        cfg = config or EnsembleConfig()
        if weights is not None:
            cfg.weights = dict(weights)
        if min_members is not None:
            if min_members < 1:
                raise PolicyError(
                    f"min_members must be >= 1, got {min_members}")
            cfg.min_members = min_members
        if strategy_options is not None:
            cfg.strategy_options = dict(strategy_options)
        self.config = cfg
        # Validate weights eagerly so a typo fails at construction,
        # not at 3am during the first decide().
        if self.config.weights:
            normalize_weights(self.config.weights, names)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "ensemble": True,
            "strategy": self.strategy,
            "strategies_available": sorted(STRATEGIES),
            "members": [m.name for m in self.members],
            "min_members": self.config.min_members,
        }

    def supports(self, spec: DecisionSpec) -> bool:
        return any(m.supports(spec) for m in self.members)

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        validate_state(state)
        start = time.perf_counter()
        votes = collect_votes(
            self.members, state, spec, context,
            weights=self.config.weights,
            min_members=self.config.min_members,
            ensemble_name=self.name)
        combiner = get_strategy(self.strategy)
        ctx = StrategyContext(
            spec=spec,
            options=dict(self.config.strategy_options),
            fitted=None)
        result = combiner(votes, ctx)
        result.backend = self.name
        result.latency_ms = (time.perf_counter() - start) * 1000.0
        validate_result(result, spec)
        return result

    def decide_batch(self, states: List[Mapping[str, Any]],
                     spec: DecisionSpec,
                     context: Optional[Mapping[str, Any]] = None
                     ) -> List[DecisionResult]:
        """Evaluate a batch of states (slice 122 optimizes this path)."""
        return [self.evaluate(s, spec, context) for s in states]

    def member_votes(self, state: Mapping[str, Any],
                     spec: DecisionSpec,
                     context: Optional[Mapping[str, Any]] = None
                     ) -> List[MemberVote]:
        """Collect member ballots without combining (introspection)."""
        validate_state(state)
        return collect_votes(
            self.members, state, spec, context,
            weights=self.config.weights,
            min_members=self.config.min_members,
            ensemble_name=self.name)
