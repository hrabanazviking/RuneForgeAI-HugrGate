"""Privacy enforcement — system-level guardrails. Slice 40.

The per-decision ``DecisionPolicy`` already gates remote backends, but policy
is application-supplied and can be loosened by mistake. ``PrivacyGuard`` is
the operator-level backstop: when remote inference is *forbidden* at this
level, remote backends are excluded at **selection time** — before any state
ever flows to them — and any direct attempt raises ``PrivacyViolation``.

It also owns provenance redaction: records must never carry raw state when
the privacy class forbids it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, List, Mapping, Optional

from hugrgate.backend import Backend
from hugrgate.errors import BackendUnavailable, PrivacyViolation
from hugrgate.policy import DecisionPolicy
from hugrgate.provenance import DecisionRecord

__all__ = [
    "REMOTE_MODES",
    "NON_CACHEABLE_PRIVACY_CLASSES",
    "PrivacyGuard",
]

REMOTE_MODES = ("allow", "forbidden")
#: Privacy classes whose data must never touch the decision cache or
#: leave the process in provenance records.
NON_CACHEABLE_PRIVACY_CLASSES = frozenset({"strict"})


class PrivacyGuard:
    """Operator-level privacy enforcement.

    Parameters
    ----------
    remote_inference:
        ``"allow"`` — defer to each decision's ``DecisionPolicy``.
        ``"forbidden"`` — remote backends are blocked at selection time
        even if the policy would permit them; direct attempts raise
        ``PrivacyViolation``.
    redact_provenance:
        When True, provenance records produced under this guard have raw
        state material scrubbed.
    """

    def __init__(self, remote_inference: str = "allow",
                 redact_provenance: bool = True):
        if remote_inference not in REMOTE_MODES:
            raise ValueError(f"remote_inference must be one of {REMOTE_MODES}, "
                             f"got {remote_inference!r}")
        self.remote_inference = remote_inference
        self.redact_provenance = redact_provenance

    # -- selection-time enforcement -------------------------------------

    def remote_allowed(self, backend: Backend, policy: DecisionPolicy) -> bool:
        """True only if both the guard and the policy permit remote use."""
        if backend.is_remote and self.remote_inference == "forbidden":
            return False
        return policy.backend_allowed(backend.name, backend.is_remote)

    def check_backend(self, backend: Backend, policy: DecisionPolicy) -> None:
        """Attempt gate: raise before any state flows to a blocked backend.

        Raises
        ------
        PrivacyViolation
            When remote inference is forbidden at guard level and the
            backend is remote.
        BackendUnavailable
            When the decision policy itself disallows the backend.
        """
        if backend.is_remote and self.remote_inference == "forbidden":
            raise PrivacyViolation(
                f"remote backend {backend.name!r} blocked: remote_inference "
                f"is forbidden by the privacy guard",
                backend=backend.name)
        if not policy.backend_allowed(backend.name, backend.is_remote):
            raise BackendUnavailable(
                f"backend {backend.name!r} blocked by decision policy",
                backend=backend.name)

    def filter_backends(self, backends: Iterable[Backend],
                        policy: DecisionPolicy) -> List[Backend]:
        """Selection-time filter: blocked backends never become candidates."""
        return [b for b in backends if self.remote_allowed(b, policy)]

    # -- cache policy ----------------------------------------------------

    @staticmethod
    def cache_allowed(policy: DecisionPolicy) -> bool:
        """Never cache when the privacy class forbids retention."""
        return policy.privacy_class not in NON_CACHEABLE_PRIVACY_CLASSES

    # -- redaction -------------------------------------------------------

    @staticmethod
    def redact_state(state: Mapping[str, Any]) -> dict:
        """Return a state-shaped mapping with every value masked."""
        return {k: "<redacted>" for k in state.keys()}

    def redact_record(self, record: DecisionRecord) -> DecisionRecord:
        """Return a copy of ``record`` with raw state material scrubbed.

        Drops any state keys/values from ``metadata`` and marks the record
        as redacted. Idempotent.
        """
        metadata = {k: v for k, v in record.metadata.items()
                    if k not in ("state_keys", "state", "raw_state")}
        metadata["redacted"] = True
        return replace(record, metadata=metadata)

    def provenance_redaction_needed(self,
                                    policy: Optional[DecisionPolicy]) -> bool:
        """Whether records for this policy must be redacted."""
        if self.redact_provenance:
            return True
        return policy is not None and \
            policy.privacy_class in NON_CACHEABLE_PRIVACY_CLASSES
