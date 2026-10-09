"""Ground-truth attachment. Slice 304.

Outcomes (slice 303) say what was *observed*; ground truth says what
was *verified*. The distinction matters: an observed "success" can
later be re-labeled a failure by audit, human review, or a delayed
measurement. Ground truth is the verified label stream that slices
311 (outcome-conditioned retrieval), 320 (counterfactuals), and 322
(calibration) learn from.

Semantics:

- One ground truth per episode; once set it is immutable unless
  ``supersede=True`` is passed, in which case the displaced truth is
  preserved in ``episode.annotations["ground_truth_revisions"]`` —
  history is corrected, never silently rewritten.
- ``source`` names who verified the label (human reviewer, audit job,
  delayed sensor); empty sources are rejected.
- :func:`outcome_agrees` compares an attached outcome against ground
  truth when the label is comparable (bool or one of the outcome
  kinds); :func:`consistency_report` scans a history for episodes
  where verified truth contradicts the observed outcome — the raw
  material for slice 323's adversarial detectors.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hugrgate.memory.outcomes import OUTCOME_KINDS, Outcome
from hugrgate.memory.query import MemoryQuery

if TYPE_CHECKING:  # pragma: no cover - typing only
    from hugrgate.memory.history import DecisionHistory

__all__ = [
    "GroundTruth",
    "consistency_report",
    "outcome_agrees",
]


@dataclass(frozen=True)
class GroundTruth:
    """A verified label for a remembered decision."""

    label: Any
    confidence: float = 1.0
    source: str = "unknown"
    verified_at: float = 0.0
    note: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"ground-truth confidence must be in [0, 1], got "
                f"{self.confidence}")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("ground-truth source must be a non-empty "
                             "string")
        if self.verified_at <= 0:
            object.__setattr__(self, "verified_at", time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "source": self.source,
            "verified_at": self.verified_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> GroundTruth:
        """Rebuild from :meth:`to_dict`; ``ValueError`` on bad data."""
        if not isinstance(d, Mapping) or "label" not in d \
                or "source" not in d:
            raise ValueError(
                "GroundTruth.from_dict needs 'label' and 'source' keys")
        return cls(
            label=d["label"],
            confidence=d.get("confidence", 1.0),
            source=d["source"],
            verified_at=d.get("verified_at") or 0.0,
            note=d.get("note") or "",
        )


def outcome_agrees(truth: GroundTruth, outcome: Outcome) -> bool | None:
    """Do verified truth and observed outcome agree?

    Returns ``None`` when the label is not comparable to an outcome
    kind (anything other than a bool or one of success/failure/partial).
    """
    label = truth.label
    if isinstance(label, bool):
        expected = "success" if label else "failure"
    elif isinstance(label, str) and label in OUTCOME_KINDS:
        expected = label
    else:
        return None
    if outcome.kind == "partial":
        return None  # partial outcomes are not verdicts
    return outcome.kind == expected


def consistency_report(history: DecisionHistory) -> list[dict[str, Any]]:
    """Episodes where ground truth contradicts the attached outcome.

    Each entry carries ``episode_id``, the outcome kind, the truth
    label, and the truth source — the audit trail a reviewer needs.
    Episodes without both attachments, or with non-comparable labels,
    are skipped.
    """
    report = []
    episodes = history.find(
        MemoryQuery(has_outcome=True, has_ground_truth=True))
    for episode in episodes:
        outcome = episode.outcome
        truth = episode.ground_truth
        if outcome is None or truth is None:
            continue
        if outcome_agrees(truth, outcome) is False:
            report.append({
                "episode_id": episode.episode_id,
                "outcome_kind": outcome.kind,
                "truth_label": truth.label,
                "truth_source": truth.source,
            })
    return report
