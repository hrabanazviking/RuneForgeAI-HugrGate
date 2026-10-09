"""Policy propagation across the cluster. Slice 210.

Nodes must agree on the *safety* posture of remote work: if one node
forbids remote inference, the cluster must not route remote work
through it on a weaker policy's say-so. :class:`PolicyPropagator`
keeps a versioned cluster policy per node and merges inbound policies
with a documented, fail-closed semantic:

**Strictest-wins** (safety fields — the cluster is never more
permissive than its strictest member):

- ``minimum_probability`` → ``max``
- ``remote_inference`` → ``and`` (one veto disables)
- ``privacy_class`` → ``"strict"`` if any member says strict
- ``maximum_latency_ms`` / ``max_cost`` → ``min`` of the set members
- ``allowed_backends`` → intersection (a backend the cluster may use
  must be allowed everywhere it runs)
- ``fallback_behavior`` → most conservative
  (``abstain`` > ``escalate`` > ``safe_default``)
- ``review_band`` → envelope union (widest band anyone asked for)

**Newest-wins** (preference fields — no safety impact):

- ``preferred_backends`` → from the highest
  ``(version, timestamp, node_id)``

Every merge bumps the local version, so the merged policy itself
propagates and the cluster converges.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from hugrgate.errors import PolicyError, SpecError
from hugrgate.policy import DecisionPolicy
from hugrgate.serde import policy_from_dict, policy_to_dict

__all__ = [
    "PolicyPropagator",
    "PolicyVersion",
    "merge_policies",
]

#: Conservative ordering for fallback_behavior (index 0 wins).
_FALLBACK_ORDER = ("abstain", "escalate", "safe_default")


@dataclass(order=True)
class PolicyVersion:
    """Monotonic version stamp. Ordered: higher wins."""

    version: int
    timestamp: float = field(default_factory=time.time)
    node_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or self.version < 0:
            raise SpecError("policy version must be a non-negative int")

    def bump(self, node_id: str = "") -> PolicyVersion:
        return PolicyVersion(self.version + 1, time.time(),
                             node_id or self.node_id)

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "timestamp": self.timestamp,
                "node_id": self.node_id}

    @classmethod
    def from_dict(cls, data: Any) -> PolicyVersion:
        if not isinstance(data, dict):
            raise SpecError("policy version must be a dict")
        try:
            return cls(version=data["version"],
                       timestamp=data.get("timestamp", 0.0),
                       node_id=data.get("node_id", ""))
        except (KeyError, TypeError) as e:
            raise SpecError(
                f"bad policy version: {e}") from e


def _conservative_fallback(a: str, b: str) -> str:
    order = {name: i for i, name in enumerate(_FALLBACK_ORDER)}
    return a if order.get(a, 99) <= order.get(b, 99) else b


def _union_band(a: tuple | None, b: tuple | None) -> tuple | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), max(a[1], b[1]))


def merge_policies(local: DecisionPolicy,
                   remote: DecisionPolicy) -> DecisionPolicy:
    """Merge two policies with the strictest-wins semantic above."""
    allowed: list[str] | None
    if local.allowed_backends is None:
        allowed = (list(remote.allowed_backends)
                   if remote.allowed_backends is not None else None)
    elif remote.allowed_backends is None:
        allowed = list(local.allowed_backends)
    else:
        allowed = [b for b in local.allowed_backends
                   if b in remote.allowed_backends]
    latencies = [v for v in (local.maximum_latency_ms,
                             remote.maximum_latency_ms)
                 if v is not None]
    costs = [v for v in (local.max_cost, remote.max_cost)
             if v is not None]
    privacy = ("strict" if "strict" in (local.privacy_class,
                                        remote.privacy_class)
               else "standard")
    return DecisionPolicy(
        minimum_probability=max(local.minimum_probability,
                                remote.minimum_probability),
        maximum_latency_ms=min(latencies) if latencies else None,
        remote_inference=local.remote_inference and remote.remote_inference,
        allowed_backends=allowed,
        preferred_backends=list(
            local.preferred_backends or remote.preferred_backends or []),
        fallback_behavior=_conservative_fallback(
            local.fallback_behavior, remote.fallback_behavior),
        privacy_class=privacy,
        max_cost=min(costs) if costs else None,
        review_band=_union_band(local.review_band, remote.review_band),
    )


class PolicyPropagator:
    """Versioned cluster policy with merge-on-receive.

    ``policy`` is the effective cluster policy; ``version`` stamps it.
    :meth:`update` sets a new local policy (bumps the version);
    :meth:`receive` merges an inbound ``(policy_dict, version_dict)``
    pair and reports whether the effective policy changed.
    """

    def __init__(self, node_id: str = "",
                 policy: DecisionPolicy | None = None) -> None:
        self._node_id = node_id
        self._policy = policy or DecisionPolicy()
        self._version = PolicyVersion(0, node_id=node_id)
        # preferred_backends follows newest-wins, tracked separately
        self._preferred_version = PolicyVersion(0, node_id=node_id)

    @property
    def policy(self) -> DecisionPolicy:
        return self._policy

    @property
    def version(self) -> PolicyVersion:
        return self._version

    def update(self, policy: DecisionPolicy) -> PolicyVersion:
        """Adopt a new local policy (operator action)."""
        if not isinstance(policy, DecisionPolicy):
            raise PolicyError(
                f"policy must be a DecisionPolicy, got "
                f"{type(policy).__name__}")
        self._policy = policy
        self._version = self._version.bump(self._node_id)
        self._preferred_version = self._version
        return self._version

    def receive(self, policy_dict: dict[str, Any],
                version_dict: dict[str, Any]) -> bool:
        """Merge an inbound policy. Returns True when the effective
        policy changed (caller should re-propagate)."""
        remote_version = PolicyVersion.from_dict(version_dict)
        remote_policy = policy_from_dict(policy_dict)
        merged = merge_policies(self._policy, remote_policy)
        # newest-wins for the preference field
        if remote_version > self._preferred_version:
            merged.preferred_backends = list(
                remote_policy.preferred_backends or [])
            self._preferred_version = remote_version
        changed = policy_to_dict(merged) != policy_to_dict(self._policy)
        self._policy = merged
        self._version = self._version.bump(self._node_id)
        return changed

    def snapshot(self) -> dict[str, Any]:
        """Wire shape: ``{"policy": {...}, "version": {...}}``."""
        return {"policy": policy_to_dict(self._policy),
                "version": self._version.to_dict()}
