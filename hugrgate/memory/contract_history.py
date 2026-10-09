"""Contract history features. Slice 313.

"How has this *contract* fared over time?" Contracts group decisions
by the decision contract they served: the ``contract_id`` carried in
record metadata (propagated by
:func:`hugrgate.privacy_provenance.privacy_preserving_record` since
this slice — previously it was dropped, making contract history
impossible). Decisions without a contract id fall back to a synthetic
key derived from the spec's value-space shape, so ad-hoc decisions
still aggregate meaningfully; such groups are marked ``synthetic``.

Each :class:`ContractHistory` reports decision counts, acceptance
rate, outcome distribution, success rate among labeled decisions
(``None`` when unlabeled — never 0), the backends that served the
contract, mean probability, and first/last seen timestamps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import EpisodeLike, HistoryLike

__all__ = [
    "ContractHistory",
    "contract_histories",
    "contract_key_for",
]


def _spec_signature(spec: dict[str, Any]) -> str:
    """Stable readable signature of a spec's value-space shape."""
    parts = [str(spec.get("type", "?"))]
    for key in ("options", "levels", "labels"):
        values = spec.get(key)
        if values:
            parts.append(f"{key}=" + "|".join(str(v) for v in values))
    if spec.get("type") == "binary" and spec.get("statement"):
        parts.append("stmt=" + str(spec["statement"])[:40])
    if spec.get("type") == "numeric":
        parts.append(f"range={spec.get('minimum')}:{spec.get('maximum')}")
    return ":".join(parts)


def contract_key_for(episode: EpisodeLike) -> str:
    """Group key for an episode's contract.

    ``"contract:<id>"`` when the record carries a contract id,
    otherwise ``"spec:<signature>"`` (synthetic).
    """
    metadata = episode.record.metadata or {}
    contract_id = metadata.get("contract_id")
    if isinstance(contract_id, str) and contract_id:
        return f"contract:{contract_id}"
    return f"spec:{_spec_signature(episode.record.spec)}"


@dataclass(frozen=True)
class ContractHistory:
    """Aggregate track record of one decision contract."""

    key: str
    contract_id: str | None
    synthetic: bool
    spec_type: str
    decision_count: int
    accepted_count: int
    accepted_rate: float
    outcome_counts: dict[str, int] = field(default_factory=dict)
    success_rate: float | None = None
    backends: tuple[str, ...] = ()
    mean_probability: float | None = None
    first_seen: float | None = None
    last_seen: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "contract_id": self.contract_id,
            "synthetic": self.synthetic,
            "spec_type": self.spec_type,
            "decision_count": self.decision_count,
            "accepted_count": self.accepted_count,
            "accepted_rate": self.accepted_rate,
            "outcome_counts": dict(self.outcome_counts),
            "success_rate": self.success_rate,
            "backends": list(self.backends),
            "mean_probability": self.mean_probability,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


def contract_histories(history: HistoryLike, *,
                       limit: int = 5000,
                       query: MemoryQuery | None = None,
                       ) -> dict[str, ContractHistory]:
    """Aggregate per-contract track records from history."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    episodes: Sequence[EpisodeLike] = history.find(
        query if query is not None else MemoryQuery())
    ordered = sorted(episodes, key=lambda e: e.recorded_at, reverse=True)
    ordered = ordered[:limit]

    groups: dict[str, list[EpisodeLike]] = {}
    for episode in ordered:
        groups.setdefault(contract_key_for(episode), []).append(episode)

    result: dict[str, ContractHistory] = {}
    for key, group in groups.items():
        first = group[0]
        metadata = first.record.metadata or {}
        raw_id = metadata.get("contract_id")
        contract_id = raw_id if isinstance(raw_id, str) and raw_id else None
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
        probabilities = [e.record.probability for e in group]
        result[key] = ContractHistory(
            key=key,
            contract_id=contract_id,
            synthetic=contract_id is None,
            spec_type=str(first.record.spec.get("type", "?")),
            decision_count=len(group),
            accepted_count=accepted,
            accepted_rate=accepted / len(group),
            outcome_counts=outcome_counts,
            success_rate=(positive / labeled if labeled else None),
            backends=tuple(sorted({e.record.backend for e in group})),
            mean_probability=(sum(probabilities) / len(probabilities)
                              if probabilities else None),
            first_seen=min(e.recorded_at for e in group),
            last_seen=max(e.recorded_at for e in group),
        )
    return result
