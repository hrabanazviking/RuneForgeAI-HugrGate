"""Domain history profiles. Slice 314.

Backends answer "who served it", contracts answer "under what terms",
domains answer "about what". A domain is the application-declared
subject area of a decision — ``spec.metadata["domain"]`` first,
``record.metadata["domain"]`` second, ``"default"`` when neither is
set. Each :class:`DomainProfile` aggregates the domain's volume,
acceptance, outcomes, top serving backends, spec-type mix, and
decay-weighted activity (how *alive* the domain is right now).
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.decay import decay_weight
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "DEFAULT_DOMAIN",
    "DomainProfile",
    "domain_for",
    "domain_profiles",
]

#: Domain used when neither spec nor record metadata names one.
DEFAULT_DOMAIN = "default"


def domain_for(episode: EpisodeLike) -> str:
    """Resolve an episode's domain (spec metadata > record metadata)."""
    spec_metadata = episode.record.spec.get("metadata") or {}
    domain = spec_metadata.get("domain")
    if isinstance(domain, str) and domain:
        return domain
    record_metadata = episode.record.metadata or {}
    domain = record_metadata.get("domain")
    if isinstance(domain, str) and domain:
        return domain
    return DEFAULT_DOMAIN


@dataclass(frozen=True)
class DomainProfile:
    """Aggregate profile of one decision domain."""

    domain: str
    decision_count: int
    accepted_rate: float
    outcome_counts: dict[str, int] = field(default_factory=dict)
    success_rate: float | None = None
    top_backends: tuple[tuple[str, int], ...] = ()
    spec_types: tuple[str, ...] = ()
    mean_probability: float | None = None
    activity: float = 0.0
    first_seen: float | None = None
    last_seen: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "decision_count": self.decision_count,
            "accepted_rate": self.accepted_rate,
            "outcome_counts": dict(self.outcome_counts),
            "success_rate": self.success_rate,
            "top_backends": [list(pair) for pair in self.top_backends],
            "spec_types": list(self.spec_types),
            "mean_probability": self.mean_probability,
            "activity": self.activity,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


def domain_profiles(history: HistoryLike, *,
                    half_life_seconds: float = 86400.0,
                    limit: int = 5000,
                    query: MemoryQuery | None = None,
                    now: float | None = None
                    ) -> dict[str, DomainProfile]:
    """Aggregate per-domain profiles from history."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    current = time.time() if now is None else now
    episodes: Sequence[EpisodeLike] = history.find(
        query if query is not None else MemoryQuery())
    ordered = sorted(episodes, key=lambda e: e.recorded_at, reverse=True)
    ordered = ordered[:limit]

    groups: dict[str, list[EpisodeLike]] = {}
    for episode in ordered:
        groups.setdefault(domain_for(episode), []).append(episode)

    result: dict[str, DomainProfile] = {}
    for domain, group in groups.items():
        accepted = sum(1 for e in group if e.record.accepted)
        outcome_counts: dict[str, int] = {}
        positive = 0
        labeled = 0
        for episode in group:
            outcome = episode.outcome
            if outcome is not None:
                labeled += 1
                outcome_counts[outcome.kind] = \
                    outcome_counts.get(outcome.kind, 0) + 1
                if outcome.is_positive():
                    positive += 1
        backend_counts = Counter(e.record.backend for e in group)
        probabilities = [e.record.probability for e in group]
        result[domain] = DomainProfile(
            domain=domain,
            decision_count=len(group),
            accepted_rate=accepted / len(group),
            outcome_counts=outcome_counts,
            success_rate=(positive / labeled if labeled else None),
            top_backends=tuple(backend_counts.most_common(3)),
            spec_types=tuple(
                sorted({str(e.record.spec.get("type", "?")) for e in group})),
            mean_probability=(sum(probabilities) / len(probabilities)
                              if probabilities else None),
            activity=sum(decay_weight(current - e.recorded_at,
                                      half_life_seconds) for e in group),
            first_seen=min(e.recorded_at for e in group),
            last_seen=max(e.recorded_at for e in group),
        )
    return result
