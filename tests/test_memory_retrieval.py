"""Slice 306 — Decision retrieval: transparent similarity+recency+outcome recall."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    DecisionHistory,
    Outcome,
    RetrievalResult,
    recall,
    retrieve,
)
from hugrgate.memory.similarity import featurize_query
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    good = hist.record(_record(backend="local", model="m1", probability=0.9))
    hist.attach_outcome(good.episode_id, Outcome(kind="success", score=0.95))
    bad = hist.record(_record(backend="local", model="m1", probability=0.85))
    hist.attach_outcome(bad.episode_id, Outcome(kind="failure"))
    hist.record(_record(backend="remote", model="m2", probability=0.3))
    return hist


def test_retrieve_ranks_and_explains():
    hist = _history()
    query = featurize_query(spec={"type": "binary"}, backend="local",
                            model="m1", probability=0.9)
    results = retrieve(hist, query, k=3)
    assert len(results) == 3
    assert all(isinstance(r, RetrievalResult) for r in results)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    text = results[0].explain()
    assert "score=" in text and "similarity=" in text
    assert "backend=" in text


def test_outcome_bonus_prefers_success():
    hist = DecisionHistory()
    good = hist.record(_record(probability=0.7))
    bad = hist.record(_record(probability=0.7))
    hist.attach_outcome(good.episode_id, Outcome(kind="success"))
    hist.attach_outcome(bad.episode_id, Outcome(kind="failure"))
    query = featurize_query(spec={"type": "binary"}, probability=0.7)
    # outcome-only scoring: success must outrank failure
    results = retrieve(hist, query, k=2, alpha=0.0, beta=0.0, gamma=1.0,
                       now=time.time())
    assert len(results) == 2
    assert results[0].episode.episode_id == good.episode_id
    assert results[0].outcome_bonus == 1.0
    assert results[1].outcome_bonus == 0.0


def test_recency_matters():
    hist = DecisionHistory()
    old = hist.record(_record(probability=0.7))
    # age the first episode by rewriting recorded_at via internal copy
    hist._by_id[old.episode_id].recorded_at -= 30 * 86400
    new = hist.record(_record(probability=0.7))
    query = featurize_query(spec={"type": "binary"}, probability=0.7)
    results = retrieve(hist, query, k=2, alpha=0.0, beta=1.0, gamma=0.0,
                       half_life_seconds=86400.0, now=time.time())
    assert results[0].episode.episode_id == new.episode_id
    assert results[0].recency > results[1].recency


def test_min_score_filters():
    hist = _history()
    query = featurize_query(spec={"type": "binary"})
    assert retrieve(hist, query, k=5, min_score=0.9999) == []


def test_retrieve_validation():
    hist = _history()
    query = featurize_query(backend="local")
    with pytest.raises(ValueError):
        retrieve(hist, query, alpha=-1.0)
    with pytest.raises(ValueError):
        retrieve(hist, query, alpha=0.0, beta=0.0, gamma=0.0)
    with pytest.raises(ValueError):
        retrieve(hist, query, k=-1)
    with pytest.raises(ValueError):
        retrieve(hist, query, min_score=2.0)
    assert retrieve(hist, query, k=0) == []


def test_recall_convenience():
    hist = _history()
    results = recall(hist, k=2, backend="local", model="m1",
                     spec={"type": "binary"}, probability=0.9)
    assert len(results) == 2
    assert all(r.episode.record.backend == "local" for r in results)


def test_recall_empty_history():
    assert recall(DecisionHistory(), backend="local") == []


def test_exclude_ids():
    hist = _history()
    query = featurize_query(backend="local")
    first = retrieve(hist, query, k=1)[0]
    rest = retrieve(hist, query, k=5,
                    exclude_ids={first.episode.episode_id})
    assert all(r.episode.episode_id != first.episode.episode_id
               for r in rest)


def test_retrieve_empty_query_features():
    hist = _history()
    assert retrieve(hist, {}, k=3) == []
