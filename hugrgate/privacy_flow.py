"""Data-flow policy engine. Slice 228.

Where should data be allowed to move? :class:`DataFlowPolicy`
answers that for a single planned flow — a :class:`FlowRequest`
describing *what* (privacy class, field sensitivity levels,
local-only fields) moves *where* (destination backend, its trust
level, remoteness, jurisdiction) — and returns a :class:`FlowDecision`
(``allow`` / ``redact`` / ``deny``) with machine-readable reasons.
Denials raise :class:`~hugrgate.errors.DataFlowDenied`.

Rules are evaluated in a fixed, documented order so decisions are
deterministic and explainable (slice 246 renders them):

1. class eligibility — a ``forbidden``-class payload never flows remote;
2. trust floor — destination trust must meet the class minimum;
3. jurisdiction — remote destinations outside the allowed set are denied;
4. field levels — fields above the remote clearance are stripped
   (``redact`` mode) or deny the flow (strict mode);
5. local-only fields are always stripped from remote flows.

The engine takes abstract inputs (trust levels, jurisdictions) so
slices 229-230 can supply attested values without changing the rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import DataFlowDenied
from hugrgate.privacy import semantics_for, trust_rank
from hugrgate.privacy_labels import Sensitivity

__all__ = [
    "DataFlowPolicy",
    "FlowDecision",
    "FlowRequest",
]

#: Jurisdiction code for in-process destinations. Local flows are
#: always jurisdiction-clean: data never crosses a border.
LOCAL_JURISDICTION = "local"


def _coerce_level(level: Sensitivity | str | int) -> Sensitivity:
    if isinstance(level, Sensitivity):
        return level
    if isinstance(level, str):
        try:
            return Sensitivity[level.upper()]
        except KeyError:
            raise ValueError(
                f"unknown sensitivity: {level!r}") from None
    return Sensitivity(int(level))


@dataclass
class FlowRequest:
    """A planned movement of data to a destination backend."""

    privacy_class: str
    dst_name: str
    dst_remote: bool = False
    dst_trust: str = "enclave"
    dst_jurisdiction: str = LOCAL_JURISDICTION
    field_levels: Mapping[str, Sensitivity | str | int] = field(
        default_factory=dict)
    local_only_fields: Iterable[str] = ()
    jurisdictions_allowed: frozenset[str] | set[str] | None = None

    def __post_init__(self):
        object.__setattr__(self, "field_levels",
                           {str(k): _coerce_level(v)
                            for k, v in self.field_levels.items()})
        object.__setattr__(self, "local_only_fields",
                           frozenset(str(f)
                                     for f in self.local_only_fields))
        if self.jurisdictions_allowed is not None:
            object.__setattr__(self, "jurisdictions_allowed",
                               frozenset(self.jurisdictions_allowed))


@dataclass
class FlowDecision:
    """The engine's verdict for one :class:`FlowRequest`."""

    allowed: bool
    action: str  # "allow" | "redact" | "deny"
    redactions: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def raise_if_denied(self) -> FlowDecision:
        """Raise :class:`DataFlowDenied` when the flow was denied."""
        if not self.allowed:
            raise DataFlowDenied(
                f"data flow to {self._dst!r} denied: "
                + "; ".join(self.reasons),
                reasons=list(self.reasons),
                redactions=list(self.redactions))
        return self

    # Carried for the error message; set by the policy, not the caller.
    _dst: str = ""


class DataFlowPolicy:
    """Evaluates :class:`FlowRequest` objects against ordered rules.

    Parameters
    ----------
    max_remote_level:
        Highest field :class:`Sensitivity` that may flow to a remote
        destination without being stripped. ``SECRET`` fields are
        denied remote transit by default.
    redact_instead_of_deny:
        When True, over-clearance and local-only fields are stripped
        (``redact`` decision) instead of denying the flow. Hard rules
        (class eligibility, trust floor, jurisdiction) always deny.
    """

    def __init__(self,
                 max_remote_level: Sensitivity | str | int = Sensitivity.CONFIDENTIAL,
                 redact_instead_of_deny: bool = False):
        if isinstance(max_remote_level, str):
            max_remote_level = Sensitivity[max_remote_level.upper()]
        self.max_remote_level = Sensitivity(max_remote_level)
        self.redact_instead_of_deny = redact_instead_of_deny

    def check(self, request: FlowRequest) -> FlowDecision:
        """Evaluate a flow; raises :class:`DataFlowDenied` on denial."""
        sem = semantics_for(request.privacy_class)
        reasons: list[str] = []
        redactions: list[str] = []

        # Rule 1 — class eligibility.
        if request.dst_remote and not sem["remote_eligible"]:
            reasons.append(
                f"privacy_class {request.privacy_class!r} forbids remote "
                f"flows")
            return self._deny(request, reasons)

        # Rule 2 — trust floor.
        if trust_rank(request.dst_trust) < trust_rank(sem["min_trust"]):
            reasons.append(
                f"destination trust {request.dst_trust!r} below class "
                f"minimum {sem['min_trust']!r} for "
                f"{request.privacy_class!r}")
            return self._deny(request, reasons)

        # Rule 3 — jurisdiction.
        allowed = request.jurisdictions_allowed
        if (request.dst_remote and allowed is not None
                and request.dst_jurisdiction != LOCAL_JURISDICTION
                and request.dst_jurisdiction not in allowed):
            reasons.append(
                f"destination jurisdiction {request.dst_jurisdiction!r} "
                f"not in allowed {sorted(allowed)}")
            return self._deny(request, reasons)

        # Rule 4 — field levels (remote destinations only).
        if request.dst_remote:
            for fname, level in request.field_levels.items():
                if fname in request.local_only_fields:
                    continue  # handled by rule 5
                if level > self.max_remote_level:
                    if self.redact_instead_of_deny:
                        redactions.append(fname)
                        reasons.append(
                            f"field {fname!r} ({level}) above remote "
                            f"clearance; stripped")
                    else:
                        reasons.append(
                            f"field {fname!r} ({level}) above remote "
                            f"clearance {self.max_remote_level}")
                        return self._deny(request, reasons)

        # Rule 5 — local-only fields never leave the process.
        if request.dst_remote:
            for fname in sorted(request.local_only_fields):
                if fname in request.field_levels:
                    redactions.append(fname)
                    reasons.append(f"local-only field {fname!r} stripped "
                                   f"from remote flow")

        if redactions:
            decision = FlowDecision(allowed=True, action="redact",
                                    redactions=sorted(set(redactions)),
                                    reasons=reasons)
        else:
            reasons.append("all data-flow rules passed")
            decision = FlowDecision(allowed=True, action="allow",
                                    reasons=reasons)
        decision._dst = request.dst_name
        return decision

    @staticmethod
    def _deny(request: FlowRequest, reasons: list[str]) -> FlowDecision:
        decision = FlowDecision(allowed=False, action="deny",
                                reasons=reasons)
        decision._dst = request.dst_name
        return decision.raise_if_denied()

    def to_dict(self) -> dict[str, Any]:
        return {"max_remote_level": self.max_remote_level.name.lower(),
                "redact_instead_of_deny": self.redact_instead_of_deny}
