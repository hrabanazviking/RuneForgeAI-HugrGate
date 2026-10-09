"""Outcome attachment. Slice 303.

A decision without an observed outcome is a story without an ending:
:func:`attach_outcome` records what *actually happened* after the
runtime acted on a decision — success, failure, or partial — plus an
optional numeric score. Outcomes are what turn the history from a log
into training data for slices 305-322 (similarity, retrieval,
calibration, counterfactuals).

Semantics:

- One outcome per episode; re-attaching requires ``overwrite=True``
  so accidental double-reporting is loud, not silent.
- Outcomes are immutable value objects (frozen dataclass); the
  history swaps the reference under its lock.
- ``observed_at`` defaults to now but is settable, so backfilled or
  delayed outcomes (cf. ``hugrgate.adaptive.feedback``) keep their true
  timestamps.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "OUTCOME_KINDS",
    "Outcome",
]

#: Allowed outcome kinds.
OUTCOME_KINDS = ("success", "failure", "partial")


@dataclass(frozen=True)
class Outcome:
    """What actually happened after a remembered decision."""

    kind: str
    score: float | None = None
    observed_at: float = 0.0
    note: str = ""
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in OUTCOME_KINDS:
            raise ValueError(
                f"outcome kind must be one of {OUTCOME_KINDS}, got "
                f"{self.kind!r}")
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError(
                f"outcome score must be in [0, 1], got {self.score}")
        if self.observed_at <= 0:
            object.__setattr__(self, "observed_at", time.time())
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError(
                f"outcome latency_ms must be >= 0, got {self.latency_ms}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "score": self.score,
            "observed_at": self.observed_at,
            "note": self.note,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Outcome:
        """Rebuild from :meth:`to_dict`; ``ValueError`` on bad data."""
        try:
            kind = d["kind"]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Outcome.from_dict needs a 'kind' key: {exc}") from exc
        return cls(
            kind=kind,
            score=d.get("score"),
            observed_at=d.get("observed_at") or 0.0,
            note=d.get("note") or "",
            latency_ms=d.get("latency_ms"),
        )

    def is_positive(self) -> bool:
        """True for success, or partial with score >= 0.5."""
        if self.kind == "success":
            return True
        if self.kind == "partial" and self.score is not None:
            return self.score >= 0.5
        return False
