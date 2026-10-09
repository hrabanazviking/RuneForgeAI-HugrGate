"""Slice 302 — Queryable provenance store: MemoryQuery + store.scan."""

from __future__ import annotations

import pytest

from hugrgate.errors import MemoryError
from hugrgate.memory import (
    DecisionHistory,
    MemoryQuery,
    find_in_provenance,
)
from hugrgate.provenance import DecisionRecord, ProvenanceStore


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    hist.record(_record(backend="local", probability=0.9, accepted=True),
                tags=["a"])
    hist.record(_record(backend="remote", probability=0.4, accepted=False),
                tags=["a", "b"], privacy_class="sensitive")
    hist.record(_record(backend="local", probability=0.6, accepted=True,
                        fallback_used=True),
                tags=["b"])
    return hist


def test_empty_query_matches_all():
    hist = _history()
    assert len(hist.find(MemoryQuery())) == 3


def test_filter_by_backend():
    hist = _history()
    got = hist.find(MemoryQuery(backends={"local"}))
    assert len(got) == 2
    assert all(e.record.backend == "local" for e in got)


def test_filter_accepted_and_fallback():
    hist = _history()
    assert len(hist.find(MemoryQuery(accepted=False))) == 1
    assert len(hist.find(MemoryQuery(fallback_used=True))) == 1
    assert len(hist.find(MemoryQuery(accepted=True, fallback_used=True))) == 1


def test_probability_range():
    hist = _history()
    got = hist.find(MemoryQuery(min_probability=0.5, max_probability=0.9))
    assert {e.record.probability for e in got} == {0.6, 0.9}


def test_tags_any_and_all():
    hist = _history()
    assert len(hist.find(MemoryQuery(tags_any={"a"}))) == 2
    assert len(hist.find(MemoryQuery(tags_all={"a", "b"}))) == 1
    assert len(hist.find(MemoryQuery(tags_all={"a"}))) == 2


def test_privacy_class_filter():
    hist = _history()
    got = hist.find(MemoryQuery(privacy_classes={"sensitive"}))
    assert len(got) == 1
    assert got[0].privacy_class == "sensitive"


def test_sort_and_pagination():
    hist = _history()
    got = hist.find(MemoryQuery(sort_by="probability", descending=False,
                                limit=2))
    assert [e.record.probability for e in got] == [0.4, 0.6]
    page2 = hist.find(MemoryQuery(sort_by="probability", descending=False,
                                  limit=2, offset=2))
    assert [e.record.probability for e in page2] == [0.9]
    assert hist.find(MemoryQuery(limit=2, offset=99)) == []
    assert hist.find(MemoryQuery(limit=0)) == []


def test_sort_by_latency():
    hist = DecisionHistory()
    hist.record(_record(latency_ms=30.0))
    hist.record(_record(latency_ms=5.0))
    got = hist.find(MemoryQuery(sort_by="latency_ms", descending=False))
    assert [e.record.latency_ms for e in got] == [5.0, 30.0]


def test_find_returns_copies():
    hist = _history()
    got = hist.find(MemoryQuery())
    victim_id = got[0].episode_id
    got[0].record.value = "tampered"
    assert hist.get(victim_id).record.value is True


def test_find_rejects_wrong_type():
    hist = _history()
    with pytest.raises(TypeError):
        hist.find({"backends": {"local"}})


def test_query_validation():
    with pytest.raises(ValueError):
        MemoryQuery(sort_by="color")
    with pytest.raises(ValueError):
        MemoryQuery(limit=-1)
    with pytest.raises(ValueError):
        MemoryQuery(offset=-2)
    with pytest.raises(ValueError):
        MemoryQuery(min_probability=1.5)
    with pytest.raises(ValueError):
        MemoryQuery(min_probability=0.8, max_probability=0.2)
    with pytest.raises(ValueError):
        MemoryQuery(recorded_after=10.0, recorded_before=5.0)


def test_explain_renders_plan():
    q = MemoryQuery(backends={"local"}, accepted=True, limit=5)
    text = q.explain()
    assert "local" in text and "accepted=True" in text and "limit=5" in text
    assert MemoryQuery().explain() == "MemoryQuery(match-all)"


def test_provenance_scan_primitive():
    store = ProvenanceStore()
    store.append(_record(backend="local", probability=0.9))
    store.append(_record(backend="remote", probability=0.1))
    got = store.scan(lambda r: r.probability > 0.5)
    assert len(got) == 1
    assert got[0].backend == "local"
    # deep copies: mutating the result cannot touch the store
    got[0].backend = "tampered"
    assert store.scan(lambda r: True)[0].backend == "local"


def test_find_in_provenance():
    store = ProvenanceStore()
    store.append(_record(backend="local", probability=0.9, accepted=True))
    store.append(_record(backend="remote", probability=0.2, accepted=False))
    got = find_in_provenance(store, MemoryQuery(backends={"local"}))
    assert len(got) == 1 and got[0].backend == "local"
    got = find_in_provenance(
        store, MemoryQuery(sort_by="probability", descending=True, limit=1))
    assert got[0].probability == 0.9
    # memory-only filter is rejected, not silently ignored
    with pytest.raises(MemoryError):
        find_in_provenance(store, MemoryQuery(tags_any={"a"}))
    with pytest.raises(MemoryError):
        find_in_provenance(store, MemoryQuery(has_outcome=True))


def test_find_in_provenance_rejects_wrong_types():
    store = ProvenanceStore()
    with pytest.raises(TypeError):
        find_in_provenance("nope", MemoryQuery())
    with pytest.raises(TypeError):
        find_in_provenance(store, "nope")
