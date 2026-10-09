"""Slice 311 — Outcome-conditioned retrieval: learn from wins / failures."""

from __future__ import annotations

import pytest

from hugrgate.memory import (
    DecisionHistory,
    GroundTruth,
    MemoryQuery,
    Outcome,
    retrieve,
    retrieve_conditioned,
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
    good = hist.record(_record())
    hist.attach_outcome(good.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(good.episode_id,
                             GroundTruth(label=True, source="audit"))
    bad = hist.record(_record())
    hist.attach_outcome(bad.episode_id, Outcome(kind="failure"))
    hist.attach_ground_truth(bad.episode_id,
                             GroundTruth(label=False, source="audit"))
    hist.record(_record())  # no outcome
    return hist


def _query():
    return featurize_query(spec={"type": "binary"}, backend="local",
                           probability=0.8)


def test_success_conditioned():
    hist = _history()
    results = retrieve_conditioned(hist, _query(), k=5)
    assert len(results) == 1
    assert results[0].episode.outcome is not None
    assert results[0].episode.outcome.kind == "success"


def test_failure_conditioned():
    hist = _history()
    results = retrieve_conditioned(hist, _query(), k=5,
                                   outcome_kinds={"failure"})
    assert len(results) == 1
    assert results[0].episode.outcome.kind == "failure"


def test_unknown_excluded_by_default():
    hist = _history()
    results = retrieve_conditioned(hist, _query(), k=5,
                                   outcome_kinds=None)
    assert len(results) == 2  # only the two with outcomes


def test_include_unknown():
    hist = _history()
    results = retrieve_conditioned(hist, _query(), k=5, outcome_kinds=None,
                                   include_unknown=True)
    assert len(results) == 3


def test_require_truth_agreement():
    hist = DecisionHistory()
    honest = hist.record(_record())
    hist.attach_outcome(honest.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(honest.episode_id,
                             GroundTruth(label=True, source="audit"))
    lying = hist.record(_record())
    hist.attach_outcome(lying.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(lying.episode_id,
                             GroundTruth(label=False, source="audit"))
    results = retrieve_conditioned(hist, _query(), k=5,
                                   outcome_kinds={"success"},
                                   require_truth_agreement=True)
    assert [r.episode.episode_id for r in results] == [honest.episode_id]


def test_truth_agreement_needs_truth():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    results = retrieve_conditioned(hist, _query(), k=5,
                                   require_truth_agreement=True)
    assert results == []


def test_invalid_kind_rejected():
    hist = _history()
    with pytest.raises(ValueError):
        retrieve_conditioned(hist, _query(), outcome_kinds={"triumph"})


def test_episodes_subset_scoring():
    # retrieve() accepts a caller-supplied episode subset (slice 311)
    hist = _history()
    subset = [e for e in hist.find(MemoryQuery())
              if e.outcome is not None and e.outcome.kind == "failure"]
    results = retrieve(hist, _query(), k=5, episodes=subset)
    assert len(results) == 1
    assert results[0].episode.outcome.kind == "failure"


def test_conditioned_empty_result():
    hist = DecisionHistory()
    hist.record(_record())
    assert retrieve_conditioned(hist, _query(), k=5) == []
