"""Slice 16 — memory recall pagination: limit/offset on recall/find."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    DecisionHistory,
    recall,
    retrieve,
)
from hugrgate.memory.query import MemoryQuery
from hugrgate.memory.similarity import featurize_query
from hugrgate.provenance import DecisionRecord

N = 60  # enough episodes to exercise windows


def _record(i: int) -> DecisionRecord:
    return DecisionRecord(
        request_hash=f"req-{i:04d}",
        spec={"type": "binary", "slot": i % 4},
        backend="local" if i % 2 == 0 else "remote",
        model="m1",
        value=(i % 2 == 0),
        probability=0.1 + (i / N) * 0.8,
    )


def _history(n: int = N) -> DecisionHistory:
    hist = DecisionHistory()
    base = time.time() - n
    for i in range(n):
        record = _record(i)
        record.timestamp = base + i
        hist.record(record, tags=(f"t{i % 3}",))
        # Nudge recorded_at apart so ordering is deterministic.
        stored = hist._episodes[-1]
        stored.recorded_at = base + i
    return hist


def _ids(results) -> list[str]:
    return [r.episode.episode_id for r in results]


def _ep_ids(episodes) -> list[str]:
    return [e.episode_id for e in episodes]


# -- find -----------------------------------------------------------------


def test_find_pagination_is_window_of_unpaginated():
    hist = _history()
    full = hist.find(MemoryQuery(sort_by="recorded_at", descending=False))
    full_ids = _ep_ids(full)
    assert len(full_ids) == N
    page = hist.find(MemoryQuery(sort_by="recorded_at", descending=False),
                     limit=10, offset=20)
    assert _ep_ids(page) == full_ids[20:30]


def test_find_limit_only_and_offset_only():
    hist = _history()
    full = hist.find(MemoryQuery(sort_by="recorded_at", descending=False))
    full_ids = _ep_ids(full)
    assert _ep_ids(hist.find(MemoryQuery(sort_by="recorded_at",
                                         descending=False), limit=5)) == full_ids[:5]
    assert _ep_ids(hist.find(MemoryQuery(sort_by="recorded_at",
                                         descending=False), offset=N - 3)) == full_ids[-3:]


def test_find_defaults_preserve_behavior():
    hist = _history()
    assert _ep_ids(hist.find(MemoryQuery())) == _ep_ids(
        hist.find(MemoryQuery(), limit=None, offset=0))
    # Query-level pagination still applies first; find() pages after it.
    query = MemoryQuery(limit=10, offset=0, descending=False)
    assert len(hist.find(query, limit=4, offset=2)) == 4


def test_find_pagination_beyond_end_is_empty():
    hist = _history()
    assert hist.find(MemoryQuery(), offset=N) == []
    assert hist.find(MemoryQuery(), offset=N + 100, limit=10) == []
    assert hist.find(MemoryQuery(), limit=0) == []


def test_find_pagination_validation():
    hist = _history()
    with pytest.raises(ValueError):
        hist.find(MemoryQuery(), limit=-1)
    with pytest.raises(ValueError):
        hist.find(MemoryQuery(), offset=-1)


# -- retrieve -------------------------------------------------------------


def _query():
    return featurize_query(spec={"type": "binary"}, backend="local",
                           model="m1", probability=0.5)


def test_retrieve_pagination_is_window_of_unpaginated():
    hist = _history()
    full = retrieve(hist, _query(), k=N, now=time.time())
    full_ids = _ids(full)
    assert len(full_ids) == N
    page = retrieve(hist, _query(), k=N, limit=10, offset=20,
                    now=time.time())
    assert _ids(page) == full_ids[20:30]


def test_retrieve_pagination_after_k():
    hist = _history()
    top5 = retrieve(hist, _query(), k=5, now=time.time())
    assert _ids(retrieve(hist, _query(), k=5, limit=2, offset=1,
                        now=time.time())) == _ids(top5)[1:3]
    assert len(retrieve(hist, _query(), k=5, limit=1,
                        now=time.time())) == 1


def test_retrieve_defaults_preserve_behavior():
    hist = _history()
    assert _ids(retrieve(hist, _query(), k=7, now=time.time())) == _ids(
        retrieve(hist, _query(), k=7, limit=None, offset=0, now=time.time()))
    assert retrieve(hist, _query(), k=3, offset=100,
                    now=time.time()) == []
    assert retrieve(hist, _query(), k=3, limit=0,
                    now=time.time()) == []


def test_retrieve_pagination_validation():
    hist = _history()
    with pytest.raises(ValueError):
        retrieve(hist, _query(), limit=-1)
    with pytest.raises(ValueError):
        retrieve(hist, _query(), offset=-2)


# -- recall ---------------------------------------------------------------


def test_recall_pagination_is_window_of_unpaginated():
    hist = _history()
    full = recall(hist, k=N, spec={"type": "binary"}, backend="local",
                  now=time.time())
    full_ids = _ids(full)
    page = recall(hist, k=N, spec={"type": "binary"}, backend="local",
                  limit=7, offset=13, now=time.time())
    assert _ids(page) == full_ids[13:20]


def test_recall_defaults_preserve_behavior():
    hist = _history()
    assert _ids(recall(hist, k=4, spec={"type": "binary"},
                       now=time.time())) == _ids(
        recall(hist, k=4, spec={"type": "binary"}, limit=None, offset=0,
               now=time.time()))
    with pytest.raises(ValueError):
        recall(hist, spec={"type": "binary"}, limit=-1)


def test_recall_offset_beyond_ranked_is_empty():
    hist = _history()
    assert recall(hist, k=5, spec={"type": "binary"}, offset=50,
                  now=time.time()) == []
