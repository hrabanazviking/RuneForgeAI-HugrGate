"""Outcome feedback API. Slice 127.

Route decisions are only half the story: the router needs to know how
the chosen backend *did*. :class:`OutcomeFeedbackAPI` is the single
write path for outcome labels — human grades, downstream success flags,
or automated checks — onto telemetry events (slice 126).

Contract:

- ``quality`` is required and must lie in ``[0, 1]``; ``label`` is an
  optional categorical verdict (``"success"`` / ``"failure"`` /
  ``"partial"`` — the only accepted labels, so a typo can never sneak
  in as a new class, mirroring ``DecisionPolicy``'s privacy-class rule).
- Unknown ``request_id`` raises ``KeyError`` — feedback for a decision
  the router never logged is a bug, not a guess.
- Outcomes are immutable once attached: overwriting history would poison
  offline learning (slice 131). Pass ``allow_overwrite=True`` only when
  the caller explicitly takes responsibility.
- Every outcome carries its ``source`` and ``received_at`` timestamp, so
  learners can weight or filter by provenance.

The API also offers :meth:`record_immediate`, which logs a route
decision *and* its immediately-known quality (e.g. the result's
probability and policy verdict) in one call — the common case for
online bandit updates (slice 130).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

from hugrgate.errors import SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

from hugrgate.adaptive.telemetry import RouteEvent, TelemetryStore

__all__ = [
    "OUTCOME_LABELS",
    "OutcomeRecord",
    "OutcomeFeedbackAPI",
]

#: The only outcome labels with defined semantics.
OUTCOME_LABELS = ("success", "failure", "partial")


@dataclass(frozen=True)
class OutcomeRecord:
    """An attached outcome: what happened, who said so, when."""

    request_id: str
    quality: float
    label: Optional[str] = None
    source: str = "human"
    received_at: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.quality <= 1.0:
            raise SpecError(
                f"outcome quality must be in [0,1], got {self.quality!r}")
        if self.label is not None and self.label not in OUTCOME_LABELS:
            raise SpecError(
                f"unknown outcome label {self.label!r}; expected one of "
                f"{list(OUTCOME_LABELS)}")
        if not isinstance(self.source, str) or not self.source:
            raise SpecError("outcome source must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality": self.quality,
            "label": self.label,
            "source": self.source,
            "received_at": self.received_at,
        }


class OutcomeFeedbackAPI:
    """Write path for outcome labels onto routing telemetry."""

    def __init__(self, store: TelemetryStore) -> None:
        self.store = store

    def record_outcome(self, request_id: str, *, quality: float,
                       label: Optional[str] = None,
                       source: str = "human",
                       received_at: Optional[float] = None,
                       allow_overwrite: bool = False) -> OutcomeRecord:
        """Attach an outcome to a logged route decision."""
        if request_id not in self.store:
            raise KeyError(
                f"no telemetry for request_id {request_id!r}: feedback "
                f"must reference a logged route decision")
        record = OutcomeRecord(
            request_id=request_id,
            quality=quality,
            label=label,
            source=source,
            received_at=time.time() if received_at is None else received_at,
        )
        if allow_overwrite:
            event = self.store.get(request_id)
            assert event is not None
            # Surgical overwrite: allowed only when the caller says so.
            self.store._events[request_id] = RouteEvent(
                **{**event.__dict__, "outcome": record.to_dict()})
            self.store._append_line({
                "schema": self.store.stats()["schema"],
                "kind": "outcome",
                "request_id": request_id,
                "outcome": record.to_dict(),
                "attached_at": record.received_at,
                "overwrote": True,
            })
        else:
            self.store.attach_outcome(request_id, record.to_dict())
        return record

    def record_immediate(self, *, spec: DecisionSpec,
                         features: Mapping[str, float],
                         candidates: list,
                         propensities: Mapping[str, float],
                         chosen: str,
                         policy_version: str,
                         result: DecisionResult,
                         policy: Optional[DecisionPolicy] = None,
                         request_id: Optional[str] = None,
                         ) -> str:
        """Log a route decision plus its immediate quality in one call.

        The immediate quality is the result's reported probability when
        the policy accepted it, 0.0 when the policy abstained — an
        honest, available-now proxy that delayed labels (slice 128) may
        later refine.
        """
        verdict = policy.evaluate(result) if policy is not None else "accept"
        quality = result.probability if verdict == "accept" else 0.0
        event = RouteEvent(
            request_id=request_id or TelemetryStore.new_request_id(),
            timestamp=time.time(),
            spec=spec.to_dict(),
            features=dict(features),
            candidates=list(candidates),
            propensities=dict(propensities),
            chosen=chosen,
            policy_version=policy_version,
            privacy_class=policy.privacy_class if policy else "standard",
            latency_ms=result.latency_ms,
            cost=float(result.metadata.get("cost", 0.0)),
            energy_wh=float(result.metadata.get("energy_wh", 0.0)),
            immediate_quality=quality,
            metadata={
                "policy_verdict": verdict,
                "backend": result.backend,
                "model": result.model,
            },
        )
        rid = self.store.record(event)
        self.record_outcome(rid, quality=quality, source="immediate",
                            label="success" if verdict == "accept"
                            else "failure")
        return rid
