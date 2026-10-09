"""Slice 015 — provenance integrity.

"Append-only" was a docstring, not a property: callers could mutate
history through held references, ``recent(0)`` returned *everything*
(``[-0:] == [0:]``), and nothing detected edits to the stored list.
"""

from __future__ import annotations

import pytest

from hugrgate.provenance import DecisionRecord, ProvenanceStore
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec

SPEC = DecisionSpec(type="categorical", options=["a", "b"])
STATE = {"x": 1}


def _record(value="a", prob=0.8):
    other = "b" if value == "a" else "a"
    r = DecisionResult(value=value, probability=prob,
                       distribution={value: prob, other: 1.0 - prob})
    return DecisionRecord.from_decision(STATE, SPEC, r,
                                        policy_threshold=0.5)


def _store(n=3):
    s = ProvenanceStore()
    for i in range(n):
        s.append(_record())
    return s


def test_append_rejects_non_records():
    s = ProvenanceStore()
    with pytest.raises(TypeError):
        s.append({"request_hash": "x"})
    assert s.count() == 0


def test_recent_zero_returns_empty():
    assert _store().recent(0) == []


def test_recent_negative_rejected():
    with pytest.raises(ValueError):
        _store().recent(-1)


def test_mutating_input_after_append_does_not_rewrite_history():
    s = ProvenanceStore()
    rec = _record(value="a")
    s.append(rec)
    rec.value = "b"  # caller mutates their own object
    assert s.recent(1)[0].value == "a"


def test_mutating_read_result_does_not_rewrite_history():
    s = _store()
    first = s.recent(1)[0]
    first.value = "tampered"
    assert s.recent(1)[0].value == "a"
    found = s.by_hash(first.request_hash)
    found.value = "tampered"
    assert s.by_hash(first.request_hash).value == "a"


def test_chain_links_records():
    s = _store(3)
    recs = s._records  # internal: chain shape, not caller API
    assert recs[0].prev_hash == ""
    assert recs[1].prev_hash == recs[0].record_hash
    assert recs[2].prev_hash == recs[1].record_hash
    assert len({r.record_hash for r in recs}) == 3


def test_verify_chain_passes_on_intact_history():
    assert _store(5).verify_chain() is True
    assert ProvenanceStore().verify_chain() is True  # empty is valid


def test_verify_chain_detects_tampering():
    s = _store(3)
    s._records[1].value = "evil"  # direct attack on the stored list
    assert s.verify_chain() is False


def test_verify_chain_detects_reordering():
    s = _store(3)
    s._records[0], s._records[1] = s._records[1], s._records[0]
    assert s.verify_chain() is False


def test_by_hash_returns_latest_match():
    s = ProvenanceStore()
    r1, r2 = _record(value="a"), _record(value="b")
    s.append(r1)
    s.append(r2)
    assert r1.request_hash == r2.request_hash  # same state+spec
    assert s.by_hash(r1.request_hash).value == "b"
    assert s.by_hash("nope") is None
