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
with a one-call ``append_decision`` entry point, and
:class:`SealedProvenanceStore` additionally seals every record body
at rest (slice 242): the on-disk/in-memory chain commits to
*ciphertext*, while the plaintext record (with its own hashes) rides
inside the sealed body.
"""

from __future__ import annotations

import copy
import hashlib
import pickle
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from hugrgate.errors import SealError
from hugrgate.policy import DecisionPolicy
from hugrgate.privacy import provenance_mode_for
from hugrgate.privacy_crypto import SealedBox, require_key
from hugrgate.privacy_redact import redact_metadata
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

__all__ = [
    "PrivacyAwareProvenanceStore",
    "SealedProvenanceStore",
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
    # Slice 313: the decision contract id is an identifier, not state
    # payload — it survives every privacy mode so contract history
    # (hugrgate.memory.contract_history) can group decisions by the
    # contract they served. Never a state value, never PII.
    contract_id = result.metadata.get("contract_id")
    if isinstance(contract_id, str) and contract_id:
        metadata["contract_id"] = contract_id
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


class SealedProvenanceStore(PrivacyAwareProvenanceStore):
    """A provenance store that seals every record body at rest.

    Each appended record is chained (``prev_hash``/``record_hash``
    over its canonical plaintext form), then pickled and sealed with
    :class:`SealedBox`. The stored wrapper keeps the chain hashes,
    ``request_hash``, ``timestamp``, and ``privacy_class`` marker in
    plaintext — so retention purges and chain-link checks work
    without the key — while the full record body is opaque.

    :meth:`verify_chain` checks both the outer links and, by
    unsealing, the inner content hashes; any tampering fails
    closed with ``False`` (``SealError`` inside ``recent`` /
    ``by_hash``).
    """

    def __init__(self, key: bytes, *, namespace: str = "provenance",
                 max_records: int | None = None):
        super().__init__(max_records=max_records)
        self._key = require_key(key)
        self._namespace = str(namespace)

    def _associated(self, record_hash: str) -> bytes:
        return (self._namespace + ":" + record_hash).encode()

    def _seal(self, record: DecisionRecord) -> DecisionRecord:
        blob = SealedBox.seal(self._key, pickle.dumps(record),
                              associated=self._associated(
                                  record.record_hash))
        return replace(
            record,
            metadata={"sealed": True,
                      "sealed_blob": blob,
                      "privacy_class": record.metadata.get(
                          "privacy_class")})

    def _unseal(self, wrapper: DecisionRecord) -> DecisionRecord:
        blob = wrapper.metadata.get("sealed_blob")
        if not wrapper.metadata.get("sealed") or \
                not isinstance(blob, (bytes, bytearray)):
            raise SealError("provenance entry is not sealed",
                            reason="unexpected-type")
        try:
            inner = pickle.loads(SealedBox.open(
                self._key, bytes(blob),
                associated=self._associated(wrapper.record_hash)))
        except SealError as e:
            raise SealError(f"provenance entry tampered: {e}",
                            reason="auth") from e
        if not isinstance(inner, DecisionRecord):
            raise SealError("sealed payload is not a DecisionRecord",
                            reason="unexpected-type")
        return inner

    def append(self, record: DecisionRecord) -> None:
        if not isinstance(record, DecisionRecord):
            raise TypeError(
                f"ProvenanceStore only stores DecisionRecord, got "
                f"{type(record).__name__}")
        stored = copy.deepcopy(record)
        with self._lock:
            # Chain the *plaintext* record first, then seal the body.
            # The wrapper reuses the inner hashes as the outer links,
            # so the on-disk chain commits to ciphertext while staying
            # structurally verifiable without the key.
            stored.prev_hash = (self._records[-1].record_hash
                                if self._records else self._floor_hash)
            stored.record_hash = hashlib.sha256(
                (stored.prev_hash +
                 self._canonical(stored)).encode()).hexdigest()
            self._records.append(self._seal(stored))
            while (self._max_records is not None
                   and len(self._records) > self._max_records):
                dropped = self._records.pop(0)
                self._floor_hash = dropped.record_hash
                self._evicted += 1

    def recent(self, n: int = 10) -> list[DecisionRecord]:
        if n < 0:
            raise ValueError(f"recent(n) needs n >= 0, got {n}")
        if n == 0:
            return []
        with self._lock:
            wrappers = list(self._records[-n:])
        return [copy.deepcopy(self._unseal(w)) for w in wrappers]

    def by_hash(self, request_hash: str) -> DecisionRecord | None:
        with self._lock:
            wrappers = list(self._records)
        for w in reversed(wrappers):
            if w.request_hash == request_hash:
                return copy.deepcopy(self._unseal(w))
        return None

    def verify_chain(self) -> bool:
        """Verify outer links and inner content hashes (needs the key)."""
        with self._lock:
            wrappers = list(self._records)
            prev = self._floor_hash
        for w in wrappers:
            if w.prev_hash != prev:
                return False
            try:
                inner = self._unseal(w)
            except SealError:
                return False
            body = self._canonical(inner)
            if inner.record_hash != hashlib.sha256(
                    (inner.prev_hash + body).encode()).hexdigest():
                return False
            if (w.record_hash, w.request_hash) != \
                    (inner.record_hash, inner.request_hash):
                return False
            prev = w.record_hash
        return True

    def purge(self, predicate) -> int:
        """Chain-safe purge: survivors are re-chained and re-sealed."""
        with self._lock:
            plaintext = [self._unseal(w) for w in self._records]
            kept = [r for r in plaintext if not predicate(r)]
            removed = len(plaintext) - len(kept)
            if removed:
                self._records = []
                for r in kept:
                    self.append(r)  # RLock: re-entrant
            return removed

    def key_id_hint(self) -> str:
        """Non-secret hint identifying the key."""
        return "key:" + hashlib.sha256(self._key).hexdigest()[:8]
