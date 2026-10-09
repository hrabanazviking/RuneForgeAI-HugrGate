"""Slice 416 — provenance tamper tests.

Proves the chain detects edits/reorders, documents the tip-truncation
blind spot honestly, and proves the signed tip checkpoint closes it.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import SignatureVerificationFailed
from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.security.model_signing import ModelSigner
from hugrgate.security.provenance_guards import (
    run_tamper_suite,
    seal_tip,
    verify_tip,
)

KEY = b"t" * 32


def _records(n: int = 3) -> list[DecisionRecord]:
    return [
        DecisionRecord(request_hash=f"req{i}", spec={},
                       backend="b", model="m", value=f"v{i}")
        for i in range(n)
    ]


def _store(n: int = 3) -> ProvenanceStore:
    store = ProvenanceStore()
    for record in _records(n):
        store.append(record)
    return store


def test_chain_detects_edit():
    store = _store()
    store._records[0].value = "forged"
    assert store.verify_chain() is False


def test_chain_detects_reorder():
    store = _store()
    store._records[0], store._records[1] = \
        store._records[1], store._records[0]
    assert store.verify_chain() is False


def test_chain_misses_tip_truncation():
    """The honest gap: truncating the tip leaves a valid chain."""
    store = _store()
    del store._records[1:]
    assert store.verify_chain() is True  # blind spot, documented


def test_tip_seal_detects_truncation():
    store = _store()
    checkpoint = seal_tip(store, ModelSigner(KEY, "tip"))
    del store._records[1:]
    with pytest.raises(SignatureVerificationFailed):
        verify_tip(store, checkpoint, {"tip": KEY})


def test_tip_seal_detects_rollback():
    store = _store()
    checkpoint = seal_tip(store, ModelSigner(KEY, "tip"))
    older = _store(2)  # an earlier, perfectly valid state
    store._records = older._records  # attacker rolls the store back
    assert store.verify_chain() is True  # the chain cannot see this
    with pytest.raises(SignatureVerificationFailed):
        verify_tip(store, checkpoint, {"tip": KEY})


def test_tip_seal_detects_forged_extension():
    store = _store()
    checkpoint = seal_tip(store, ModelSigner(KEY, "tip"))
    store.append(_records(1)[0])  # unsealed append after checkpoint
    with pytest.raises(SignatureVerificationFailed):
        verify_tip(store, checkpoint, {"tip": KEY})


def test_tip_seal_round_trip():
    store = _store()
    checkpoint = seal_tip(store, ModelSigner(KEY, "tip"))
    payload = verify_tip(store, checkpoint, {"tip": KEY})
    assert payload["length"] == 3
    assert payload["tip_hash"] == store.recent(1)[0].record_hash


def test_tip_seal_wrong_key_fails():
    store = _store()
    checkpoint = seal_tip(store, ModelSigner(KEY, "tip"))
    with pytest.raises(SignatureVerificationFailed):
        verify_tip(store, checkpoint, {"tip": b"z" * 32})


def test_tampered_checkpoint_rejected():
    store = _store()
    checkpoint = seal_tip(store, ModelSigner(KEY, "tip"))
    from hugrgate.security.model_signing import SignedMetadata
    forged = SignedMetadata(metadata={"tip_hash": "x", "length": 3},
                            key_id=checkpoint.key_id,
                            signature=checkpoint.signature)
    with pytest.raises(SignatureVerificationFailed):
        verify_tip(store, forged, {"tip": KEY})


def test_tamper_suite_results():
    reports = run_tamper_suite(_records(), KEY)
    by_name = {r.attack: r for r in reports}
    # The chain sees interior edits and reorders...
    assert by_name["edit_field"].detected_by_chain is True
    assert by_name["reorder"].detected_by_chain is True
    # ...but is blind to tip truncation, rollback, and forged
    # extension — exactly the attacks the tip seal covers.
    assert by_name["truncate_tip"].detected_by_chain is False
    assert by_name["rollback"].detected_by_chain is False
    assert by_name["forged_extension"].detected_by_chain is False
    assert by_name["truncate_tip"].detected_by_tip is True
    assert by_name["rollback"].detected_by_tip is True
    assert by_name["forged_extension"].detected_by_tip is True
    # Interior edits leave the tip itself intact: the seal
    # correctly does not fire (it attests the tip, not history).
    assert by_name["edit_field"].detected_by_tip is False
    assert by_name["reorder"].detected_by_tip is False
    assert by_name["no_attack"].detected_by_chain is False
    assert by_name["no_attack"].detected_by_tip is False
