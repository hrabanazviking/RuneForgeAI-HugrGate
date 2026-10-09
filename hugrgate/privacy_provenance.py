"""Privacy-preserving provenance. Slice 238.

Provenance must explain a decision without leaking the data behind
it. :func:`privacy_preserving_record` builds a
:class:`DecisionRecord` whose state-derived metadata follows the
privacy-class ladder (slice 226):

- ``public`` / ``standard`` — state keys (never values);
- ``sensitive`` — state keys, plus optional per-field value
  fingerprints (prove *what* the input was without storing it);
- ``strict`` — fully redacted (deep-scrubbed);
- ``forbidden`` — no state-derived metadata at all.

Every record carries its ``privacy_class`` marker, so the policy is
auditable from the record alone. The integrity chain
(``prev_hash``/``record_hash``) is computed over the canonical
record *including* whatever metadata survived, so redacted and
fingerprinted records verify exactly like full ones.

:class:`PrivacyAwareProvenanceStore` wraps :class:`ProvenanceStore`
with a one-call ``append_decision`` entry point.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from typing import Any

from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import provenance_mode_for
from hugrgate.privacy_redact import redact_metadata
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "PrivacyAwareProvenanceStore",
    "fingerprint_state",
    "privacy_preserving_record",
]


def _leaf_items(state: Mapping[str, Any], prefix: str = "") -> \
        list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for key, value in state.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            items.extend(_leaf_items(value, path))
        else:
            items.append((path, value))
    return items


def fingerprint_state(state: Mapping[str, Any],
                      digest_chars: int = 16) -> dict[str, str]:
    """Deterministic per-field fingerprints (``sha256:<hex>``).

    Proves what the input was without storing it: identical inputs
    produce identical fingerprints, but the values are not
    recoverable from them.
    """
    if not 1 <= digest_chars <= 64:
        raise ValueError("digest_chars must be in [1, 64]")
    return {path: "sha256:" + hashlib.sha256(
        repr(value).encode()).hexdigest()[:digest_chars]
        for path, value in _leaf_items(state)}


def privacy_preserving_record(state: Mapping[str, Any],
                              spec: DecisionSpec,
                              result: DecisionResult,
                              policy: DecisionPolicy,
                              policy_threshold: float = 0.0,
                              fingerprints: bool = False) -> DecisionRecord:
    """Build a :class:`DecisionRecord` honoring the privacy class.

    Parameters
    ----------
    fingerprints:
        When True and the class mode is ``"keys"`` or ``"full"``,
        attach per-field value fingerprints (no raw values).
    """
    mode = provenance_mode_for(policy.privacy_class)
    scrubbed = mode in ("redacted", "none")
    record = DecisionRecord.from_decision(
        state, spec, result, policy_threshold=policy_threshold,
        redact_input=scrubbed)
    metadata: dict[str, Any] = {"privacy_class": policy.privacy_class}
    if mode in ("full", "keys"):
        metadata["state_keys"] = list(state.keys())
        if fingerprints:
            metadata["value_fingerprints"] = fingerprint_state(state)
    elif mode == "redacted":
        # from_decision already dropped state material; deep-scrub
        # anything a caller smuggled into metadata afterwards.
        metadata.update(redact_metadata(record.metadata))
    # mode == "none": no state-derived metadata whatsoever.
    metadata["redacted"] = scrubbed
    record.metadata = metadata
    return record


class PrivacyAwareProvenanceStore(ProvenanceStore):
    """A :class:`ProvenanceStore` that enforces provenance privacy."""

    def append_decision(self, state: Mapping[str, Any],
                        spec: DecisionSpec, result: DecisionResult,
                        policy: DecisionPolicy,
                        policy_threshold: float = 0.0,
                        fingerprints: bool = False) -> DecisionRecord:
        """Build a privacy-preserving record and append it."""
        record = privacy_preserving_record(
            state, spec, result, policy,
            policy_threshold=policy_threshold, fingerprints=fingerprints)
        self.append(record)
        return copy.deepcopy(record)
