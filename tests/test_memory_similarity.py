"""Slice 305 — Historical similarity search: features, cosine, top-k."""

from __future__ import annotations

import pytest

from hugrgate.memory import DecisionHistory, MemoryQuery
from hugrgate.memory.similarity import (
    SimilarityHit,
    cosine,
    featurize_episode,
    featurize_query,
    most_similar,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    hist.record(_record(backend="local", model="m1", probability=0.85))
    hist.record(_record(backend="remote", model="m2", probability=0.2))
    hist.record(_record(backend="local", model="m1", probability=0.82,
                        latency_ms=50.0))
    return hist


def test_cosine_basics():
    assert cosine({"a": 1.0}, {"a": 1.0}) == pytest.approx(1.0)
    assert cosine({"a": 1.0}, {"b": 1.0}) == 0.0
    assert cosine({}, {"a": 1.0}) == 0.0
    assert cosine({"a": 1.0}, {}) == 0.0
    assert 0.0 < cosine({"a": 1.0, "b": 1.0}, {"a": 1.0}) < 1.0


def test_cosine_symmetric():
    a = {"x": 0.5, "y": 1.0}
    b = {"y": 0.3, "z": 1.0}
    assert cosine(a, b) == pytest.approx(cosine(b, a))


def test_featurize_episode_keys():
    hist = _history()
    episode = hist.recent(1)[0]
    features = featurize_episode(episode)
    assert features["spec:type=binary"] == 1.0
    assert features["backend=local"] == 1.0
    assert features["model=m1"] == 1.0
    assert features["accepted"] == 1.0
    assert 0.0 <= features["probability"] <= 1.0


def test_featurize_query_matches_episode():
    hist = DecisionHistory()
    stored = hist.record(_record())
    from_query = featurize_query(
        spec={"type": "binary"}, backend="local", model="m1",
        probability=0.8, accepted=True, latency_ms=0.0)
    from_episode = featurize_episode(hist.get(stored.episode_id))
    # same inputs -> identical vectors -> cosine 1.0
    assert cosine(from_query, from_episode) == pytest.approx(1.0)


def test_most_similar_ranks_best_first():
    hist = _history()
    episodes = hist.find(MemoryQuery())
    query = featurize_query(spec={"type": "binary"}, backend="local",
                            model="m1", probability=0.84)
    hits = most_similar(query, episodes, k=3)
    assert len(hits) == 3
    assert all(isinstance(h, SimilarityHit) for h in hits)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    # the two local/m1 episodes outrank the remote/m2 one
    assert hits[2].episode.record.backend == "remote"
    assert hits[0].shared_features  # why-it-matched is reported


def test_identical_episode_scores_one():
    hist = DecisionHistory()
    stored = hist.record(_record())
    episode = hist.get(stored.episode_id)
    hits = most_similar(featurize_episode(episode), [episode], k=1)
    assert hits[0].score == pytest.approx(1.0)


def test_most_similar_k_and_exclude():
    hist = _history()
    episodes = hist.recent(10)
    query = featurize_query(backend="local")
    assert most_similar(query, episodes, k=0) == []
    assert len(most_similar(query, episodes, k=2)) == 2
    first = most_similar(query, episodes, k=1)[0]
    second = most_similar(query, episodes, k=2,
                          exclude_ids={first.episode.episode_id})
    assert second[0].episode.episode_id != first.episode.episode_id
    with pytest.raises(ValueError):
        most_similar(query, episodes, k=-1)


def test_most_similar_empty_inputs():
    assert most_similar({}, [], k=5) == []
    hist = _history()
    assert most_similar({}, hist.recent(10), k=5) == []


def test_tie_breaks_by_recency():
    hist = DecisionHistory()
    first = hist.record(_record())
    second = hist.record(_record())
    episodes = [hist.get(first.episode_id), hist.get(second.episode_id)]
    query = featurize_query(spec={"type": "binary"}, backend="local")
    hits = most_similar(query, episodes, k=2)
    assert hits[0].score == pytest.approx(hits[1].score)
    # identical features -> newer episode wins the tie
    assert hits[0].episode.recorded_at >= hits[1].episode.recorded_at


def test_state_keys_bounded():
    features = featurize_query(state_keys=[f"k{i}" for i in range(100)])
    keyed = [k for k in features if k.startswith("state_key=")]
    assert len(keyed) == 32
