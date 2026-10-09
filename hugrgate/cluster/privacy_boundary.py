"""Privacy boundary enforcement. Slice 211.

A cluster boundary is a trust boundary: state crossing it must be
*explicitly* allowed and *minimally* disclosed. :class:`PrivacyBoundary`
is the single choke point both ends consult:

- **Allowed?** Remote inference requires
  ``policy.remote_inference=True``. Additionally,
  ``privacy_class="strict"`` means *local-only*: under strict, state
  never leaves the node, even when ``remote_inference`` is true.
  (Strict-if-any wins in policy propagation, slice 210, so one strict
  member makes the cluster's remote posture strict.)
- **Minimal?** Fields tagged sensitive — the ``private_`` prefix by
  convention, plus an explicit set per call — are dropped before the
  envelope is built. The drop is *reported* (``redacted_fields`` in
  the request payload and result metadata), never silent: the peer's
  provenance records what it did *not* see.

Fail-closed throughout: anything ambiguous raises
:class:`PrivacyViolation`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hugrgate.errors import PrivacyViolation
from hugrgate.policy import DecisionPolicy

__all__ = [
    "SENSITIVE_PREFIX",
    "PrivacyBoundary",
]

#: State keys with this prefix are treated as sensitive and never cross
#: a node boundary.
SENSITIVE_PREFIX = "private_"


class PrivacyBoundary:
    """The choke point for state leaving the node."""

    def __init__(self, sensitive_prefix: str = SENSITIVE_PREFIX) -> None:
        if not isinstance(sensitive_prefix, str) or not sensitive_prefix:
            raise ValueError(
                "sensitive_prefix must be a non-empty string")
        self.sensitive_prefix = sensitive_prefix

    def is_sensitive(self, key: str,
                     extra: set[str] | frozenset[str] = frozenset()
                     ) -> bool:
        """True when a state key must not cross the boundary."""
        return key.startswith(self.sensitive_prefix) or key in extra

    def check_outbound_allowed(self, policy: DecisionPolicy) -> None:
        """Raise :class:`PrivacyViolation` unless the policy permits the
        state to leave this node."""
        if not isinstance(policy, DecisionPolicy):
            raise PrivacyViolation(
                "outbound check needs a DecisionPolicy")
        if policy.privacy_class == "strict":
            raise PrivacyViolation(
                "privacy_class='strict' is local-only: state must not "
                "leave the node")
        if not policy.remote_inference:
            raise PrivacyViolation(
                "remote inference blocked: policy.remote_inference "
                "is false")

    def redact_state(
            self, state: Mapping[str, Any],
            extra_sensitive: set[str] | frozenset[str] = frozenset()
    ) -> tuple[dict[str, Any], list[str]]:
        """Drop sensitive fields. Returns ``(clean_state, dropped)``.

        The input mapping is never mutated; ``dropped`` names every
        removed key so the redaction is auditable, never silent.
        """
        clean: dict[str, Any] = {}
        dropped: list[str] = []
        for key, value in state.items():
            if isinstance(key, str) and self.is_sensitive(
                    key, extra_sensitive):
                dropped.append(key)
            else:
                clean[key] = value
        return clean, sorted(dropped)

    def prepare_outbound(
            self, policy: DecisionPolicy, state: Mapping[str, Any],
            extra_sensitive: set[str] | frozenset[str] = frozenset()
    ) -> tuple[dict[str, Any], list[str]]:
        """Check permission, then redact. The single call sites use."""
        self.check_outbound_allowed(policy)
        return self.redact_state(state, extra_sensitive)
