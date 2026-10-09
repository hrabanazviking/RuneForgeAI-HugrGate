"""Slice 309 — Recency features: time-since, streaks, decayed counts."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    DecisionHistory,
    Outcome,
    RecencyFeatures,
    recency_features,
)
from hugrgate.memory.similarity import featurize_query
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _query():
    return featurize_query(spec={"type": "binary"}, backend="local",
                           model="m1", probability=0.8)


def test_empty_history():
    features = recency_features(DecisionHistory(), _query(), now=1000.0)
    assert isinstance(features, RecencyFeatures)
    assert features.time_since_last_similar is None
    assert features.last_outcome_kind is None
    assert features.success_streak == 0
    assert features.failure_streak == 0
    assert features.similar_count == 0
    assert features.effective_similar_count == 0.0
    assert features.mean_similarity == 0.0


def test_no_similar_episodes():
    hist = DecisionHistory()
    hist.record(_record(
        spec={"type": "categorical", "options": ["a", "b", "c"]},
        backend="far-away", model="other", probability=0.2, accepted=False))
    features = recency_features(hist, _query(), now=time.time())
    assert features.similar_count == 0
    assert features.time_since_last_similar is None


def test_time_since_and_last_outcome():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    now = time.time()
    features = recency_features(hist, _query(), now=now)
    assert features.similar_count == 1
    assert features.time_since_last_similar == pytest.approx(
        now - episode.recorded_at, abs=1.0)
    assert features.last_outcome_kind == "success"
    assert features.success_streak == 1
    assert features.failure_streak == 0
    assert features.effective_similar_count == pytest.approx(
        1.0, abs=0.01)
    assert features.mean_similarity > 0.5


def test_streaks():
    hist = DecisionHistory()
    # oldest -> newest: success, success, failure, success
    for kind in ("success", "success", "failure", "success"):
        episode = hist.record(_record())
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    features = recency_features(hist, _query(), now=time.time())
    assert features.similar_count == 4
    # current run at the head: one success, then a failure breaks it
    assert features.success_streak == 1
    assert features.failure_streak == 0


def test_failure_streak():
    hist = DecisionHistory()
    for kind in ("success", "failure", "failure"):
        episode = hist.record(_record())
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    features = recency_features(hist, _query(), now=time.time())
    assert features.success_streak == 0
    assert features.failure_streak == 2


def test_streak_stops_at_unknown_outcome():
    hist = DecisionHistory()
    hist.record(_record())  # no outcome attached
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    features = recency_features(hist, _query(), now=time.time())
    assert features.success_streak == 1  # unknown outcome ends the run


def test_threshold_filters():
    hist = DecisionHistory()
    hist.record(_record(backend="local", model="m1"))
    hist.record(_record(backend="other", model="other"))
    loose = recency_features(hist, _query(), similarity_threshold=0.0,
                             now=time.time())
    strict = recency_features(hist, _query(), similarity_threshold=0.99,
                              now=time.time())
    assert loose.similar_count == 2
    assert strict.similar_count <= 1


def test_validation():
    hist = DecisionHistory()
    with pytest.raises(ValueError):
        recency_features(hist, _query(), similarity_threshold=1.5)
    with pytest.raises(ValueError):
        recency_features(hist, _query(), max_candidates=0)


def test_to_dict():
    features = recency_features(DecisionHistory(), _query(), now=1.0)
    d = features.to_dict()
    assert d["similar_count"] == 0
    assert d["time_since_last_similar"] is None
    assert set(d) == {
        "time_since_last_similar", "last_outcome_kind", "success_streak",
        "failure_streak", "similar_count", "effective_similar_count",
        "mean_similarity",
    }
