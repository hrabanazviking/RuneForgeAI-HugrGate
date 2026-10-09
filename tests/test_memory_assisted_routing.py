"""Slice 321 — Memory-assisted routing: route by track record."""

from __future__ import annotations

import pytest

from hugrgate.memory import (
    DecisionHistory,
    Outcome,
    RoutingAdvice,
    advise_route,
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
    for i in range(10):
        episode = hist.record(_record(backend="local"))
        hist.attach_outcome(
            episode.episode_id,
            Outcome(kind="success" if i < 9 else "failure"))
    for i in range(10):
        episode = hist.record(_record(backend="remote"))
        hist.attach_outcome(
            episode.episode_id,
            Outcome(kind="success" if i < 3 else "failure"))
    return hist


def _query():
    return featurize_query(spec={"type": "binary"}, backend="local",
                           model="m1", probability=0.8)


def test_advises_better_backend():
    hist = _history()
    advice = advise_route(hist, _query(), ["local", "remote"])
    assert isinstance(advice, RoutingAdvice)
    assert advice.chosen == "local"
    assert advice.sufficient_data is True
    assert "local" in advice.reason
    assert advice.candidates == ("local", "remote")
    assert len(advice.estimates) == 2


def test_respects_candidate_subset():
    hist = _history()
    advice = advise_route(hist, _query(), ["remote"])
    assert advice.chosen == "remote"


def test_abstains_without_sufficient_data():
    hist = DecisionHistory()
    hist.record(_record(backend="local"))
    advice = advise_route(hist, _query(), ["local", "remote"])
    assert advice.chosen is None
    assert advice.sufficient_data is False
    assert "min_n" in advice.reason


def test_abstains_on_empty_history():
    advice = advise_route(DecisionHistory(), _query(), ["local"])
    assert advice.chosen is None
    assert advice.sufficient_data is False


def test_unknown_candidate_ignored():
    hist = _history()
    advice = advise_route(hist, _query(), ["local", "never-seen"])
    assert advice.chosen == "local"


def test_no_candidates_rejected():
    hist = _history()
    with pytest.raises(ValueError):
        advise_route(hist, _query(), [])


def test_deduplicates_candidates():
    hist = _history()
    advice = advise_route(hist, _query(), ["local", "local", "remote"])
    assert advice.candidates == ("local", "remote")
    assert advice.chosen == "local"


def test_tie_breaks_toward_more_samples():
    hist = DecisionHistory()
    for _ in range(10):
        episode = hist.record(_record(backend="a"))
        hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    for _ in range(6):
        episode = hist.record(_record(backend="b"))
        hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    advice = advise_route(hist, _query(), ["a", "b"], min_n=5)
    assert advice.chosen == "a"  # same rate, more samples


def test_to_dict():
    advice = advise_route(_history(), _query(), ["local", "remote"])
    d = advice.to_dict()
    assert d["chosen"] == "local"
    assert d["sufficient_data"] is True
    assert len(d["estimates"]) == 2
