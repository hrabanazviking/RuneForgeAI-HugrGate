"""Memory replay. Slice 319.

"Would today's policy make the same calls on yesterday's traffic?"
:func:`replay` re-runs stored episodes through a caller-supplied
``decide`` function and compares replayed decisions against the
recorded ones. This is how policy changes get validated *before*
they touch live traffic: a new threshold, a new backend preference,
a recalibrated model — replay the month, read the drift.

``decide`` receives a copy of the episode's spec dict and returns
``(value, probability)``. A ``decide`` that raises for an episode is
counted in ``errors`` — one bad episode must not abort the replay.
Value equality uses ``==`` with a ``repr`` fallback for exotic
values; probability drift is the absolute difference.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.types import HistoryLike

__all__ = [
    "ReplayReport",
    "ReplayResult",
    "replay",
]

#: decide(spec_dict) -> (value, probability).
DecideFn = Callable[[dict[str, Any]], tuple[Any, float]]


def _values_equal(a: Any, b: Any) -> bool:
    try:
        return bool(a == b)
    except Exception:  # noqa: BLE001 - exotic __eq__ must not break replay
        return repr(a) == repr(b)


@dataclass(frozen=True)
class ReplayResult:
    """Recorded vs replayed decision for one episode."""

    episode_id: str
    recorded_value: Any
    replayed_value: Any
    value_match: bool
    recorded_probability: float
    replayed_probability: float | None
    prob_drift: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "recorded_value": self.recorded_value,
            "replayed_value": self.replayed_value,
            "value_match": self.value_match,
            "recorded_probability": self.recorded_probability,
            "replayed_probability": self.replayed_probability,
            "prob_drift": self.prob_drift,
        }


@dataclass
class ReplayReport:
    """Aggregate outcome of :func:`replay`."""

    total: int = 0
    replayed: int = 0
    value_matches: int = 0
    errors: int = 0
    mean_abs_prob_drift: float | None = None
    mismatches: list[ReplayResult] = field(default_factory=list)
    error_episodes: list[str] = field(default_factory=list)

    @property
    def value_match_rate(self) -> float | None:
        """Fraction of replayed episodes with matching values."""
        if not self.replayed:
            return None
        return self.value_matches / self.replayed

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "replayed": self.replayed,
            "value_matches": self.value_matches,
            "errors": self.errors,
            "mean_abs_prob_drift": self.mean_abs_prob_drift,
            "value_match_rate": self.value_match_rate,
            "mismatches": [m.to_dict() for m in self.mismatches],
            "error_episodes": list(self.error_episodes),
        }


def replay(history: HistoryLike, decide: DecideFn, *,
           query: MemoryQuery | None = None,
           limit: int = 1000) -> ReplayReport:
    """Replay episodes through ``decide``; compare with recorded values."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    episodes: Sequence = history.find(
        query if query is not None else MemoryQuery())
    report = ReplayReport(total=min(len(episodes), limit))
    drifts: list[float] = []
    for episode in list(episodes)[:limit]:
        record = episode.record
        try:
            value, probability = decide(copy.deepcopy(record.spec))
        except Exception:  # noqa: BLE001 - counted, never fatal
            report.errors += 1
            report.error_episodes.append(episode.episode_id)
            continue
        if not isinstance(probability, (int, float)):
            report.errors += 1
            report.error_episodes.append(episode.episode_id)
            continue
        probability = float(probability)
        match = _values_equal(record.value, value)
        drift = abs(record.probability - probability)
        drifts.append(drift)
        report.replayed += 1
        if match:
            report.value_matches += 1
        else:
            report.mismatches.append(ReplayResult(
                episode_id=episode.episode_id,
                recorded_value=record.value,
                replayed_value=value,
                value_match=False,
                recorded_probability=record.probability,
                replayed_probability=probability,
                prob_drift=drift,
            ))
    report.mean_abs_prob_drift = (sum(drifts) / len(drifts)
                                  if drifts else None)
    return report
