"""JSON serde helpers shared by the server, daemon, CLI and SDK.

Slice 021: these lived in :mod:`hugrgate.client`, which forced
:mod:`hugrgate.server` to import the client while the client lazily
imported the server — a module cycle. This neutral module breaks it:
both sides import from here, and neither imports the other.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from hugrgate.errors import PolicyError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult

__all__ = [
    "policy_to_dict",
    "policy_from_dict",
    "result_from_dict",
]

#: Keys accepted by :func:`policy_from_dict`. Unknown keys are rejected
#: loudly (slice 008): a misspelled key must never silently fall back
#: to its default.
_POLICY_KEYS = frozenset({
    "minimum_probability", "maximum_latency_ms", "remote_inference",
    "allowed_backends", "preferred_backends", "fallback_behavior",
    "privacy_class", "max_cost", "review_band",
})


def policy_to_dict(policy: DecisionPolicy) -> Dict[str, Any]:
    """Serialize a :class:`DecisionPolicy` to plain JSON-compatible dict."""
    return policy.to_dict()


def policy_from_dict(d: Mapping[str, Any]) -> DecisionPolicy:
    """Rebuild a :class:`DecisionPolicy` from :func:`policy_to_dict` output."""
    unknown = set(d) - _POLICY_KEYS
    if unknown:
        raise PolicyError(
            f"unknown policy key(s): {sorted(unknown)}; "
            f"expected keys: {sorted(_POLICY_KEYS)}")
    review_band = d.get("review_band")
    return DecisionPolicy(
        minimum_probability=d.get("minimum_probability", 0.0),
        maximum_latency_ms=d.get("maximum_latency_ms"),
        remote_inference=d.get("remote_inference", False),
        allowed_backends=d.get("allowed_backends"),
        preferred_backends=d.get("preferred_backends"),
        fallback_behavior=d.get("fallback_behavior", "abstain"),
        privacy_class=d.get("privacy_class", "standard"),
        max_cost=d.get("max_cost"),
        review_band=tuple(review_band) if review_band is not None else None,
    )


def result_from_dict(d: Mapping[str, Any]) -> DecisionResult:
    """Rebuild a :class:`DecisionResult` from ``to_dict()`` output."""
    return DecisionResult(
        value=d.get("value"),
        probability=d["probability"],
        distribution=dict(d.get("distribution") or {}),
        uncertainty=d.get("uncertainty", 0.0),
        accepted=d.get("accepted", True),
        backend=d.get("backend", "unknown"),
        model=d.get("model", "unknown"),
        latency_ms=d.get("latency_ms", 0.0),
        calibration_profile=d.get("calibration_profile", "none"),
        fallback_used=d.get("fallback_used", False),
        metadata=dict(d.get("metadata") or {}),
    )
