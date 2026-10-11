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

import json
from collections.abc import Mapping, Sequence
from typing import Any

from hugrgate.errors import PolicyError, SerdeError
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult

__all__ = [
    "COMPACT_VERSION",
    "from_canonical_json",
    "policy_from_compact",
    "policy_from_dict",
    "policy_to_compact",
    "policy_to_dict",
    "result_from_compact",
    "result_from_dict",
    "result_to_compact",
    "to_canonical_json",
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


def _as_dict(value: Any, field: str) -> dict[str, Any]:
    """Coerce an optional mapping field; SerdeError on hostile types.

    Slice 422: ``dict(value or {})`` let non-mappings escape as
    TypeError/ValueError (fuzz-found, T-16).
    """
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise SerdeError(
        f"{field} must be a mapping, got {type(value).__name__}")


def _as_pair(value: Any, field: str) -> tuple | None:
    """Coerce an optional pair field; SerdeError when not iterable."""
    if value is None:
        return None
    try:
        return tuple(value)
    except TypeError:
        raise SerdeError(
            f"{field} must be a pair, got {type(value).__name__}") from None


def policy_from_dict(d: Mapping[str, Any]) -> DecisionPolicy:
    """Rebuild a :class:`DecisionPolicy` from :func:`policy_to_dict` output."""
    # dict.keys() - frozenset avoids building an intermediate set (slice 281).
    # Slice 422: non-mapping input and mixed-type keys used to escape
    # as AttributeError/TypeError (fuzz-found, T-16).
    if not isinstance(d, Mapping):
        raise SerdeError(
            f"policy must be a mapping, got {type(d).__name__}")
    unknown = d.keys() - _POLICY_KEYS
    if unknown:
        raise PolicyError(
            f"unknown policy key(s): {sorted(unknown, key=repr)}; "
            f"expected keys: {sorted(_POLICY_KEYS)}")
    review_band = _as_pair(d.get("review_band"), "review_band")
    return DecisionPolicy(
        minimum_probability=d.get("minimum_probability", 0.0),
        maximum_latency_ms=d.get("maximum_latency_ms"),
        remote_inference=d.get("remote_inference", False),
        allowed_backends=d.get("allowed_backends"),
        preferred_backends=d.get("preferred_backends"),
        fallback_behavior=d.get("fallback_behavior", "abstain"),
        privacy_class=d.get("privacy_class", "standard"),
        max_cost=d.get("max_cost"),
        review_band=review_band,
    )


def result_from_dict(d: Mapping[str, Any]) -> DecisionResult:
    """Rebuild a :class:`DecisionResult` from ``to_dict()`` output."""
    # Slice 422: a missing "probability" used to escape as KeyError
    # (fuzz-found, T-16). Missing required keys are SerdeErrors.
    if not isinstance(d, Mapping):
        raise SerdeError(
            f"result must be a mapping, got {type(d).__name__}")
    if "probability" not in d:
        raise SerdeError("result is missing required key 'probability'")
    return DecisionResult(
        value=d.get("value"),
        probability=d["probability"],
        distribution=_as_dict(d.get("distribution"), "distribution"),
        uncertainty=d.get("uncertainty", 0.0),
        accepted=d.get("accepted", True),
        backend=d.get("backend", "unknown"),
        model=d.get("model", "unknown"),
        latency_ms=d.get("latency_ms", 0.0),
        calibration_profile=d.get("calibration_profile", "none"),
        fallback_used=d.get("fallback_used", False),
        metadata=_as_dict(d.get("metadata"), "metadata"),
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
        distribution=_as_dict(distribution, "distribution"),
        uncertainty=uncertainty if uncertainty is not None else 0.0,
        accepted=bool(accepted),
        backend=backend or "unknown",
        model=model or "unknown",
        latency_ms=latency_ms or 0.0,
        calibration_profile=calibration_profile or "none",
        fallback_used=bool(fallback_used),
        metadata=_as_dict(metadata, "metadata"),
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
        review_band=_as_pair(review_band, "review_band"),
    )


# --- canonical JSON (slice D3) -----------------------------------------------

#: Floats are rounded to this many decimal places before encoding, so that
#: float noise (e.g. 1/3 versus the literal 0.333333) normalizes to
#: identical bytes.
_CANONICAL_FLOAT_DP = 6


def _normalize_floats(value: Any) -> Any:
    """Recursively round floats to 6 decimal places (slice D3).

    Ints, strings, bools and None pass through untouched; dicts, lists and
    tuples are rebuilt with normalized elements.  Anything else passes
    through untouched so :func:`json.dumps` raises its natural TypeError.
    """
    if isinstance(value, float):
        rounded = round(value, _CANONICAL_FLOAT_DP)
        # Normalize -0.0 to 0.0 so it encodes as "0.0", not "-0.0".
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        return {k: _normalize_floats(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_floats(v) for v in value]
    return value


def to_canonical_json(obj: Any) -> str:
    """Serialize ``obj`` to canonical JSON bytes-as-str.

    Sorted keys, compact separators (no whitespace), and floats rounded to
    6 decimal places before encoding, so semantically identical values
    (modulo float noise and key order) always produce byte-identical
    output.  Non-JSON-native types raise TypeError from :func:`json.dumps`
    (no custom encoders).
    """
    return json.dumps(
        _normalize_floats(obj),
        sort_keys=True,
        separators=(",", ":"),
    )


def from_canonical_json(s: str) -> Any:
    """Decode canonical JSON back to plain Python objects."""
    return json.loads(s)
