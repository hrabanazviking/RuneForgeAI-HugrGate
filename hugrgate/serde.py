"""JSON serde helpers shared by the server, daemon, CLI and SDK.

Slice 021: these lived in :mod:`hugrgate.client`, which forced
:mod:`hugrgate.server` to import the client while the client lazily
imported the server — a module cycle. This neutral module breaks it:
both sides import from here, and neither imports the other.

Slice 281 adds a compact positional encoding alongside the canonical
dict form.  The dict form stays the stable wire contract; the compact
form is the fast path for high-frequency internal transport (cache
payloads, batch results, cluster messages): no key hashing on encode,
positional indexing on decode, and JSON-serializable so it composes
with :class:`hugrgate.zerocopy.SharedPayload`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hugrgate.errors import PolicyError, SerdeError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult

__all__ = [
    "COMPACT_VERSION",
    "policy_from_compact",
    "policy_from_dict",
    "policy_to_compact",
    "policy_to_dict",
    "result_from_compact",
    "result_from_dict",
    "result_to_compact",
]

#: Version tag heading every compact payload.  Bump when the field order
#: changes; decoders reject unknown versions loudly.
COMPACT_VERSION = 1

#: Keys accepted by :func:`policy_from_dict`. Unknown keys are rejected
#: loudly (slice 008): a misspelled key must never silently fall back
#: to its default.
_POLICY_KEYS = frozenset({
    "minimum_probability", "maximum_latency_ms", "remote_inference",
    "allowed_backends", "preferred_backends", "fallback_behavior",
    "privacy_class", "max_cost", "review_band",
})


def policy_to_dict(policy: DecisionPolicy) -> dict[str, Any]:
    """Serialize a :class:`DecisionPolicy` to plain JSON-compatible dict."""
    return policy.to_dict()


def policy_from_dict(d: Mapping[str, Any]) -> DecisionPolicy:
    """Rebuild a :class:`DecisionPolicy` from :func:`policy_to_dict` output."""
    # dict.keys() - frozenset avoids building an intermediate set (slice 281).
    unknown = d.keys() - _POLICY_KEYS
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


# --- compact positional encoding (slice 281) --------------------------------

#: Field order of the compact result payload (index 0 is the version).
_RESULT_FIELDS = (
    "value", "probability", "distribution", "uncertainty", "accepted",
    "backend", "model", "latency_ms", "calibration_profile",
    "fallback_used", "metadata",
)

#: Field order of the compact policy payload (index 0 is the version).
_POLICY_FIELDS = (
    "minimum_probability", "maximum_latency_ms", "remote_inference",
    "allowed_backends", "preferred_backends", "fallback_behavior",
    "privacy_class", "max_cost", "review_band",
)


def result_to_compact(result: DecisionResult) -> list:
    """Encode a result as a versioned positional list.

    Faster than :meth:`DecisionResult.to_dict` (no key hashing) and
    smaller on the wire.  ``distribution`` and ``metadata`` are aliased,
    not copied — treat the payload as read-only, or copy it yourself.
    JSON-serializable.
    """
    return [
        COMPACT_VERSION,
        result.value,
        result.probability,
        result.distribution,
        result.uncertainty,
        result.accepted,
        result.backend,
        result.model,
        result.latency_ms,
        result.calibration_profile,
        result.fallback_used,
        result.metadata,
    ]


def result_from_compact(data: Sequence[Any]) -> DecisionResult:
    """Decode :func:`result_to_compact` output (validates invariants)."""
    want = len(_RESULT_FIELDS) + 1
    if not isinstance(data, (list, tuple)) or len(data) != want:
        raise SerdeError(
            f"compact result must be a {want}-element list, got "
            f"{type(data).__name__} of length "
            f"{len(data) if isinstance(data, (list, tuple)) else '?'}")
    if data[0] != COMPACT_VERSION:
        raise SerdeError(
            f"unsupported compact result version {data[0]!r}; "
            f"expected {COMPACT_VERSION}")
    (_version, value, probability, distribution, uncertainty, accepted,
     backend, model, latency_ms, calibration_profile, fallback_used,
     metadata) = data
    return DecisionResult(
        value=value,
        probability=probability,
        distribution=dict(distribution or {}),
        uncertainty=uncertainty if uncertainty is not None else 0.0,
        accepted=bool(accepted),
        backend=backend or "unknown",
        model=model or "unknown",
        latency_ms=latency_ms or 0.0,
        calibration_profile=calibration_profile or "none",
        fallback_used=bool(fallback_used),
        metadata=dict(metadata or {}),
    )


def policy_to_compact(policy: DecisionPolicy) -> list:
    """Encode a policy as a versioned positional list (see above)."""
    return [
        COMPACT_VERSION,
        policy.minimum_probability,
        policy.maximum_latency_ms,
        policy.remote_inference,
        policy.allowed_backends,
        policy.preferred_backends,
        policy.fallback_behavior,
        policy.privacy_class,
        policy.max_cost,
        list(policy.review_band) if policy.review_band is not None else None,
    ]


def policy_from_compact(data: Sequence[Any]) -> DecisionPolicy:
    """Decode :func:`policy_to_compact` output."""
    want = len(_POLICY_FIELDS) + 1
    if not isinstance(data, (list, tuple)) or len(data) != want:
        raise SerdeError(
            f"compact policy must be a {want}-element list, got "
            f"{type(data).__name__}")
    if data[0] != COMPACT_VERSION:
        raise SerdeError(
            f"unsupported compact policy version {data[0]!r}; "
            f"expected {COMPACT_VERSION}")
    (_version, minimum_probability, maximum_latency_ms, remote_inference,
     allowed_backends, preferred_backends, fallback_behavior,
     privacy_class, max_cost, review_band) = data
    return DecisionPolicy(
        minimum_probability=minimum_probability,
        maximum_latency_ms=maximum_latency_ms,
        remote_inference=bool(remote_inference),
        allowed_backends=allowed_backends,
        preferred_backends=preferred_backends,
        fallback_behavior=fallback_behavior or "abstain",
        privacy_class=privacy_class or "standard",
        max_cost=max_cost,
        review_band=tuple(review_band) if review_band is not None else None,
    )
