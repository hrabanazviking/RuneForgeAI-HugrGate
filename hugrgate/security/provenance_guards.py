"""Provenance tamper detection + tip sealing. Slice 416.

Attack result: the hash chain (slice 015) detects *edits* and
*reorders* — recomputing every link catches those — but
*truncation at the tip* is invisible to ``verify_chain()``: remove
the last record and the remaining links are still consistent
(threat T-06). This module proves the gap with white-box attacks
and closes it:

- :func:`seal_tip` — HMAC-signed checkpoint (slice 405 envelopes)
  over ``(tip_hash, length, sealed_at)``: a point-in-time
  attestation of the store.
- :func:`verify_tip` — re-verifies the signature, then requires
  the store's tip hash and length to match the checkpoint.
  Truncation, rollback, and forged extension all fail.
- :func:`run_tamper_suite` — the adversarial battery: edit,
  reorder, truncate, each measured against chain verification
  and tip verification.

The checkpoint lives outside the store (operator keyring): an
attacker with memory access can rewrite the chain, but cannot
forge the seal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from hugrgate.errors import SignatureVerificationFailed
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.security.model_signing import ModelSigner, SignedMetadata

__all__ = [
    "TamperReport",
    "run_tamper_suite",
    "seal_tip",
    "verify_tip",
]


def _tip(store: ProvenanceStore) -> tuple[str, int]:
    recent = store.recent(1)
    tip_hash = recent[0].record_hash if recent else ""
    return tip_hash, store.count()


def seal_tip(store: ProvenanceStore, signer: ModelSigner) -> SignedMetadata:
    """Sign a checkpoint of the store's current tip."""
    tip_hash, length = _tip(store)
    return signer.sign({
        "tip_hash": tip_hash,
        "length": length,
        "sealed_at": time.time(),
    })


def verify_tip(store: ProvenanceStore, checkpoint: SignedMetadata,
               keys: dict[str, bytes]) -> dict[str, Any]:
    """Verify the checkpoint signature and the store's current tip.

    Returns the checkpoint payload on success; raises
    :class:`SignatureVerificationFailed` on a bad signature or a
    tip mismatch (truncation / rollback / forged extension).
    """
    first = next(iter(keys))
    payload = ModelSigner(keys[first], first).verify(checkpoint, keys)
    tip_hash, length = _tip(store)
    if payload.get("tip_hash") != tip_hash or \
            payload.get("length") != length:
        raise SignatureVerificationFailed(
            "provenance tip does not match the sealed checkpoint: "
            "the store was truncated, rolled back, or extended",
            sealed_tip=payload.get("tip_hash"),
            sealed_length=payload.get("length"),
            current_tip=tip_hash, current_length=length)
    return payload


# --- white-box attacks (adversarial fixtures) -------------------------------

def _attack_edit_field(store: ProvenanceStore) -> None:
    """Silently rewrite a stored decision value."""
    store._records[0].value = "forged"
    store._records[0].probability = 1.0


def _attack_reorder(store: ProvenanceStore) -> None:
    """Swap two records, keeping every byte otherwise intact."""
    records = store._records
    records[0], records[1] = records[1], records[0]


def _attack_truncate(store: ProvenanceStore, keep: int = 1) -> None:
    """Drop records from the tip — the chain stays consistent."""
    del store._records[keep:]


def _attack_rollback(store: ProvenanceStore, pristine: list) -> None:
    """Replace the store with an older, valid copy of itself."""
    import copy
    store._records = copy.deepcopy(pristine[:2])


def _attack_forged_extension(store: ProvenanceStore) -> None:
    """Append a well-formed but unsealed record after the checkpoint."""
    extra = DecisionRecord(request_hash="forged", spec={}, backend="b",
                           model="m", value="evil")
    store.append(extra)


@dataclass
class TamperReport:
    attack: str
    detected_by_chain: bool
    detected_by_tip: bool
    detail: str = ""


def _clone_store(records: list[DecisionRecord]) -> ProvenanceStore:
    import copy
    store = ProvenanceStore()
    store._records = copy.deepcopy(records)
    return store


def run_tamper_suite(records: list[DecisionRecord], key: bytes,
                     key_id: str = "tip") -> list[TamperReport]:
    """Attack copies of a populated store; measure both detectors.

    ``records`` are appended to a fresh store (so links are valid),
    then each attack runs against an independent copy sealed at the
    same tip.
    """
    import copy
    base = ProvenanceStore()
    for record in records:
        base.append(record)
    pristine = copy.deepcopy(base._records)
    signer = ModelSigner(key, key_id)
    checkpoint = seal_tip(base, signer)
    keys = {key_id: key}
    suite: list[TamperReport] = []

    def attempt(name: str, attack: Any) -> None:
        store = _clone_store(pristine)
        attack(store)
        chain_hit = not store.verify_chain()
        try:
            verify_tip(store, checkpoint, keys)
            tip_hit = False
        except SignatureVerificationFailed:
            tip_hit = True
        suite.append(TamperReport(name, chain_hit, tip_hit))

    attempt("edit_field", _attack_edit_field)
    attempt("reorder", _attack_reorder)
    attempt("truncate_tip", lambda s: _attack_truncate(s, keep=1))
    attempt("rollback", lambda s: _attack_rollback(s, pristine))
    attempt("forged_extension", _attack_forged_extension)
    # The pristine store itself: neither detector may fire.
    untouched = _clone_store(pristine)
    suite.append(TamperReport(
        "no_attack",
        detected_by_chain=not untouched.verify_chain(),
        detected_by_tip=False,
        detail="control"))
    try:
        verify_tip(untouched, checkpoint, keys)
    except SignatureVerificationFailed:
        suite[-1].detected_by_tip = True
    return suite
