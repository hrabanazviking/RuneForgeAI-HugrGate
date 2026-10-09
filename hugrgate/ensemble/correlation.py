"""Correlated-error detection — finding members that fail as one. Slice 115.

An ensemble whose members err together is a single model with extra
latency: the vote looks independent, but the failures are not. This
module turns the pairwise Q statistics (slice 110) into a verdict:

- every member pair with ``Q >= threshold`` is flagged;
- flagged pairs are merged into *cliques* (connected components via
  union-find): chains like a~b, b~c form one clique even when a~c is
  weak;
- each clique carries a recommendation (keep one, drop or downweight
  the rest — slice 116 acts on it).

Input is a correctness history per member (aligned boolean lists);
see :mod:`hugrgate.ensemble.diversity` for the underlying metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from hugrgate.ensemble.diversity import q_statistic
from hugrgate.errors import PolicyError

__all__ = [
    "CorrelatedPair",
    "CorrelatedErrorReport",
    "detect_correlated_errors",
]


@dataclass
class CorrelatedPair:
    """Two members whose errors move together."""

    member_a: str
    member_b: str
    q: float

    def to_dict(self) -> Dict[str, object]:
        return {"member_a": self.member_a, "member_b": self.member_b,
                "q": self.q}


@dataclass
class CorrelatedErrorReport:
    """The detection verdict."""

    pairs: List[CorrelatedPair] = field(default_factory=list)
    cliques: List[List[str]] = field(default_factory=list)
    threshold: float = 0.7
    members: List[str] = field(default_factory=list)

    @property
    def correlated(self) -> bool:
        return bool(self.pairs)

    def recommendations(self) -> List[str]:
        return [
            f"members {sorted(clique)} err together (Q >= "
            f"{self.threshold}); consider keeping one and dropping or "
            f"downweighting the rest"
            for clique in self.cliques
        ]

    def to_dict(self) -> Dict[str, object]:
        return {
            "pairs": [p.to_dict() for p in self.pairs],
            "cliques": [sorted(c) for c in self.cliques],
            "threshold": self.threshold,
            "members": list(self.members),
            "correlated": self.correlated,
            "recommendations": self.recommendations(),
        }


def _cliques(members: List[str],
             edges: List[Tuple[str, str]]) -> List[List[str]]:
    """Connected components over the flagged pairs (union-find)."""
    parent = {m: m for m in members}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        union(a, b)
    groups: Dict[str, List[str]] = {}
    for m in members:
        groups.setdefault(find(m), []).append(m)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def detect_correlated_errors(correct: Dict[str, List[bool]],
                             threshold: float = 0.7
                             ) -> CorrelatedErrorReport:
    """Flag member pairs whose errors are correlated (Q >= threshold).

    ``correct`` maps member name → aligned correctness history.
    """
    members = sorted(correct)
    if len(members) < 2:
        raise PolicyError(
            "detect_correlated_errors needs at least 2 members, "
            f"got {len(members)}")
    if not -1.0 <= threshold <= 1.0:
        raise PolicyError(
            f"threshold must be in [-1, 1], got {threshold}")
    lengths = {len(h) for h in correct.values()}
    if len(lengths) != 1:
        raise PolicyError(
            f"correctness histories must be aligned, got lengths "
            f"{sorted(lengths)}")
    if not next(iter(correct.values())):
        raise PolicyError(
            "detect_correlated_errors needs a non-empty history")
    pairs: List[CorrelatedPair] = []
    edges: List[Tuple[str, str]] = []
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            q = q_statistic(correct[a], correct[b])
            if q >= threshold:
                pairs.append(CorrelatedPair(a, b, q))
                edges.append((a, b))
    pairs.sort(key=lambda p: (-p.q, p.member_a, p.member_b))
    return CorrelatedErrorReport(
        pairs=pairs,
        cliques=_cliques(members, edges),
        threshold=threshold,
        members=members,
    )
