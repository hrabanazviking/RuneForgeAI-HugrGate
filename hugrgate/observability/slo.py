"""SLO definitions. Slice 344.

A Service-Level Objective is a contract with the future: *"this
fraction of events must be good, measured this way, over this
window."*  :class:`SLODefinition` makes the contract explicit,
validated, and serializable — the evaluator (slice 345) consumes it,
the dashboard (slice 335) displays its status, and the release gate
(slice 350) can block on it.

Definitions are immutable value objects.  Bad definitions raise
:class:`~hugrgate.errors.SLOError` at construction — an SLO that
cannot be stated precisely cannot be evaluated honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import SLOError

__all__ = [
    "SLO_KINDS",
    "SLODefinition",
]

#: The measurement kinds an SLO can be built on.
SLO_KINDS = ("availability", "latency", "abstention_rate", "custom")


@dataclass(frozen=True)
class SLODefinition:
    """An immutable service-level objective.

    - ``target``: required good-fraction in (0, 1], e.g. 0.999;
    - ``window_s``: evaluation window in seconds, positive;
    - ``kind``: one of :data:`SLO_KINDS`;
    - ``params``: kind-specific parameters, e.g.
      ``{"latency_budget_ms": 100}`` for the latency kind, or
      ``{"good_when": "verdict != 'abstain'"}`` documentation for
      custom kinds.
    """

    name: str
    target: float
    window_s: float
    kind: str = "availability"
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise SLOError("SLO name must be non-empty")
        if not 0.0 < self.target <= 1.0:
            raise SLOError(
                f"SLO target must be in (0, 1], got {self.target!r}")
        if not self.window_s > 0:
            raise SLOError(
                f"SLO window_s must be positive, got {self.window_s!r}")
        if self.kind not in SLO_KINDS:
            raise SLOError(
                f"unknown SLO kind {self.kind!r}: expected one of "
                f"{list(SLO_KINDS)}")
        if self.kind == "latency" and "latency_budget_ms" not in self.params:
            raise SLOError(
                "latency SLOs require params['latency_budget_ms']")

    @property
    def error_budget(self) -> float:
        """Allowed bad-fraction: ``1 - target``."""
        return 1.0 - self.target

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "window_s": self.window_s,
            "kind": self.kind,
            "description": self.description,
            "params": dict(self.params),
            "error_budget": self.error_budget,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SLODefinition:
        """Rebuild from :meth:`to_dict` output (ignores derived fields)."""
        try:
            return cls(
                name=data["name"],
                target=float(data["target"]),
                window_s=float(data["window_s"]),
                kind=data.get("kind", "availability"),
                description=data.get("description", ""),
                params=dict(data.get("params", {})),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SLOError(
                f"invalid SLO definition dict: {exc}") from exc
