"""Ensemble batch mode — one council session, many rulings. Slice 122.

:meth:`Ensemble.evaluate` asks every member about one state.
:meth:`Ensemble.decide_batch` used to just loop that. This module
collects ballots the efficient way: each member's :meth:`batch`
fast path is called once for the whole batch, and the ballots are
transposed so every state gets its own election.

Fault isolation mirrors :func:`collect_votes` exactly, per
(member, state):

- a member whose ``batch()`` raises falls back to per-state
  ``evaluate`` (same isolation as the single-state path);
- a ``batch()`` that returns the wrong number of results is a
  contract violation: the member is skipped for every state;
- each returned result is validated; abstention-shaped, invalid,
  or contract-violating results become skip votes with named
  reasons;
- :class:`BackendError` only when a state ends up with fewer than
  ``min_members`` usable votes.

Returns ``votes_by_state[i]`` — the ballots for ``states[i]``.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from hugrgate.backend import Backend
from hugrgate.ensemble.base import MemberVote
from hugrgate.errors import (
    Abstention,
    BackendError,
    BackendUnavailable,
    PolicyError,
    SpecError,
)
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.validation import validate_result, validate_state

__all__ = [
    "batch_collect_votes",
]


def _weight(weights: Mapping[str, float] | None,
            member: Backend) -> float:
    if weights is None:
        return 1.0
    # Same rule as collect_votes: a weights map names the members
    # that count; unnamed members get weight 0.
    return float(weights.get(member.name, 0.0))


def _skip(member_name: str, w: float, reason: str) -> MemberVote:
    return MemberVote(backend=member_name, value=None, probability=0.0,
                      distribution={}, weight=w, skipped=True,
                      skip_reason=reason)


def _coerce(member_name: str, w: float, result: DecisionResult,
            spec: DecisionSpec) -> MemberVote:
    """Turn one batch result into a ballot, skipping failures."""
    try:
        validate_result(result, spec)
    except SpecError as e:
        return _skip(member_name, w, f"invalid_result: {e}")
    if result.value is None:
        return _skip(member_name, w, "abstained_result")
    return MemberVote(
        backend=member_name,
        value=result.value,
        probability=result.probability,
        distribution=dict(result.distribution),
        weight=w,
    )


def _evaluate_one(member: Backend, w: float, state: Mapping[str, Any],
                  spec: DecisionSpec,
                  context: Mapping[str, Any] | None) -> MemberVote:
    """Per-state isolation, mirroring collect_votes."""
    if not member.supports(spec):
        return _skip(member.name, w, "unsupported_spec")
    start = time.perf_counter()
    try:
        result = member.evaluate(state, spec, context)
        validate_result(result, spec)
    except Abstention as e:
        return _skip(member.name, w, f"abstained: {e.message}")
    except (BackendError, BackendUnavailable) as e:
        return _skip(member.name, w, f"backend_error: {e.message}")
    except SpecError as e:
        return _skip(member.name, w, f"invalid_result: {e}")
    except Exception as e:  # noqa: BLE001 - isolation is the point
        return _skip(member.name, w,
                      f"unexpected_{type(e).__name__}: {e}")
    if result.value is None:
        return _skip(member.name, w, "abstained_result")
    return MemberVote(
        backend=member.name,
        value=result.value,
        probability=result.probability,
        distribution=dict(result.distribution),
        weight=w,
        latency_ms=(time.perf_counter() - start) * 1000.0,
    )


def _member_ballots(member: Backend, w: float,
                    states: list[Mapping[str, Any]],
                    spec: DecisionSpec,
                    context: Mapping[str, Any] | None
                    ) -> list[MemberVote]:
    if not member.supports(spec):
        return [_skip(member.name, w, "unsupported_spec")
                for _ in states]
    try:
        results = member.batch(states, spec, context)
    except Exception:  # noqa: BLE001 - any batch failure falls back
        # The batch path failed; per-state isolation still holds.
        return [_evaluate_one(member, w, s, spec, context)
                for s in states]
    if len(results) != len(states):
        reason = (f"batch_length_mismatch: {len(results)} results "
                  f"for {len(states)} states")
        return [_skip(member.name, w, reason) for _ in states]
    return [_coerce(member.name, w, r, spec) for r in results]


def batch_collect_votes(
        members: list[Backend],
        states: list[Mapping[str, Any]],
        spec: DecisionSpec,
        context: Mapping[str, Any] | None = None,
        weights: Mapping[str, float] | None = None,
        min_members: int = 1,
        ensemble_name: str = "ensemble") -> list[list[MemberVote]]:
    """Collect ballots for every state via members' batch fast paths."""
    if min_members < 1:
        raise PolicyError(
            f"min_members must be >= 1, got {min_members}")
    for s in states:
        validate_state(s)
    if not states:
        return []
    per_member = [_member_ballots(m, _weight(weights, m), states,
                                  spec, context)
                  for m in members]
    votes_by_state: list[list[MemberVote]] = []
    for i, _ in enumerate(states):
        votes = [ballots[i] for ballots in per_member]
        usable = [v for v in votes if not v.skipped]
        if len(usable) < min_members:
            raise BackendError(
                f"ensemble {ensemble_name!r}: only {len(usable)} of "
                f"{len(members)} members produced usable votes for "
                f"batch state {i} (need >= {min_members})")
        votes_by_state.append(votes)
    return votes_by_state
