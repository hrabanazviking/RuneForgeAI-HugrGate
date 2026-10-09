"""Ensemble adversarial tests — kick the council and see. Slice 123.

Fault isolation is only real if it holds under attack. This module
provides deterministic saboteur backends and a suite runner:

- :class:`DropoutBackend` — raises :class:`BackendError` every
  ``every``-th call (a member that keeps dying);
- :class:`CorruptBackend` — returns a self-contradictory result
  every ``every``-th call (mass ≠ probability; the contract
  catches it);
- :class:`AbstainBackend` — raises :class:`Abstention` every
  ``every``-th call;
- :class:`SlowBackend` — sleeps ``delay_seconds`` per call;
- :func:`tie_storm_members` — an evenly split electorate, to pin
  the documented tie-break;
- :func:`run_adversarial_suite` — runs named
  :class:`AdversarialCase`s and summarizes decided values, errors,
  usable-vote floors, and skip reasons.

All sabotage is deterministic (every-k-th-call patterns, no RNG),
so suites are reproducible.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from hugrgate.backend import Backend
from hugrgate.ensemble.api import Ensemble
from hugrgate.errors import Abstention, BackendError, PolicyError
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "SaboteurBackend",
    "DropoutBackend",
    "CorruptBackend",
    "AbstainBackend",
    "SlowBackend",
    "tie_storm_members",
    "AdversarialCase",
    "run_adversarial_suite",
]


class SaboteurBackend(Backend):
    """Wraps a backend, sabotaging every ``every``-th call.

    ``every=1`` sabotages always; ``every=2`` every other call; and
    so on. Call counting is per-instance and deterministic.
    """

    reason = "sabotage"

    def __init__(self, wrapped: Backend, every: int = 1):
        if every < 1:
            raise PolicyError(f"every must be >= 1, got {every}")
        self.wrapped = wrapped
        self.every = every
        self.calls = 0
        self.sabotaged = 0
        self.name = wrapped.name

    def capabilities(self) -> Dict[str, Any]:
        return self.wrapped.capabilities()

    def supports(self, spec: DecisionSpec) -> bool:
        return self.wrapped.supports(spec)

    def _sabotage(self, state: Mapping[str, Any],
                  spec: DecisionSpec,
                  context: Optional[Mapping[str, Any]]) -> DecisionResult:
        raise NotImplementedError

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        self.calls += 1
        if self.calls % self.every == 0:
            self.sabotaged += 1
            return self._sabotage(state, spec, context)
        return self.wrapped.evaluate(state, spec, context)


class DropoutBackend(SaboteurBackend):
    """The member dies: raises BackendError on sabotaged calls."""

    reason = "dropout"

    def _sabotage(self, state, spec, context):
        raise BackendError(f"member {self.name!r} dropped out")


class CorruptBackend(SaboteurBackend):
    """The member lies badly: mass contradicts probability."""

    reason = "corruption"

    def _sabotage(self, state, spec, context):
        result = self.wrapped.evaluate(state, spec, context)
        return DecisionResult(
            value=result.value,
            probability=0.99,  # contradicts the distribution mass
            distribution=dict(result.distribution),
            backend=self.name,
            model=result.model,
        )


class AbstainBackend(SaboteurBackend):
    """The member declines: raises Abstention on sabotaged calls."""

    reason = "abstention"

    def _sabotage(self, state, spec, context):
        raise Abstention(f"member {self.name!r} abstains")


class SlowBackend(Backend):
    """The member is slow but honest."""

    def __init__(self, wrapped: Backend, delay_seconds: float = 0.01):
        if delay_seconds < 0:
            raise PolicyError(
                f"delay_seconds must be >= 0, got {delay_seconds}")
        self.wrapped = wrapped
        self.delay_seconds = delay_seconds
        self.name = wrapped.name

    def capabilities(self) -> Dict[str, Any]:
        return self.wrapped.capabilities()

    def supports(self, spec: DecisionSpec) -> bool:
        return self.wrapped.supports(spec)

    def evaluate(self, state: Mapping[str, Any], spec: DecisionSpec,
                 context: Optional[Mapping[str, Any]] = None
                 ) -> DecisionResult:
        time.sleep(self.delay_seconds)
        return self.wrapped.evaluate(state, spec, context)


def tie_storm_members(n: int, values: List[str],
                      distribution: Dict[str, float]) -> List[Backend]:
    """An electorate split as evenly as possible across ``values``."""
    if n < 2:
        raise PolicyError(f"tie storm needs >= 2 members, got {n}")
    if len(values) < 2:
        raise PolicyError("tie storm needs >= 2 values")

    class _FixedVoteBackend(Backend):
        def __init__(self, name: str, value: str):
            self.name = name
            self._value = value

        def capabilities(self) -> Dict[str, Any]:
            return {"fixed_vote": True}

        def supports(self, spec: DecisionSpec) -> bool:
            return spec.type in ("categorical", "binary", "ordinal")

        def evaluate(self, state: Mapping[str, Any],
                     spec: DecisionSpec,
                     context: Optional[Mapping[str, Any]] = None
                     ) -> DecisionResult:
            return DecisionResult(
                value=self._value,
                probability=distribution[self._value],
                distribution=dict(distribution),
                backend=self.name)

    members: List[Backend] = []
    for i in range(n):
        members.append(
            _FixedVoteBackend(f"m{i}", values[i % len(values)]))
    return members


@dataclass
class AdversarialCase:
    name: str
    ensemble: Ensemble
    states: List[Mapping[str, Any]]
    spec: DecisionSpec


def _summarize(case: AdversarialCase) -> Dict[str, Any]:
    values: List[Any] = []
    errors: List[str] = []
    usable_votes: List[int] = []
    skip_reasons: Dict[str, int] = {}
    for state in case.states:
        try:
            result = case.ensemble.evaluate(state, case.spec)
        except BackendError as e:
            errors.append(str(e))
            continue
        except Exception as e:  # noqa: BLE001 - the suite surfaces it
            errors.append(f"UNEXPECTED {type(e).__name__}: {e}")
            continue
        values.append(result.value)
        ens = result.metadata.get("ensemble", {})
        usable_votes.append(ens.get("usable_votes", 0))
        for ballot in ens.get("member_votes", []):
            if ballot.get("skipped"):
                reason = ballot.get("skip_reason", "?")
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
    return {
        "name": case.name,
        "states": len(case.states),
        "decided": len(values),
        "values": values,
        "errors": errors,
        "min_usable_votes": min(usable_votes) if usable_votes else 0,
        "skip_reasons": skip_reasons,
    }


def run_adversarial_suite(cases: List[AdversarialCase]
                          ) -> Dict[str, Dict[str, Any]]:
    """Run each case; return ``{name: summary}``."""
    if not cases:
        raise PolicyError("run_adversarial_suite needs cases")
    names = [c.name for c in cases]
    if len(set(names)) != len(names):
        raise PolicyError(f"case names must be unique, got {names}")
    return {c.name: _summarize(c) for c in cases}
