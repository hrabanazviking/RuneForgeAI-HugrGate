"""Slice 303 — Outcome attachment: validation, attach, overwrite rules."""

from __future__ import annotations

import time

import pytest

from hugrgate.errors import MemoryError
from hugrgate.memory import (
    OUTCOME_KINDS,
    DecisionHistory,
    MemoryQuery,
    Outcome,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def test_outcome_kinds_constant():
    assert OUTCOME_KINDS == ("success", "failure", "partial")


def test_outcome_validation():
    with pytest.raises(ValueError):
        Outcome(kind="meh")
    with pytest.raises(ValueError):
        Outcome(kind="success", score=1.5)
    with pytest.raises(ValueError):
        Outcome(kind="success", score=-0.1)
    with pytest.raises(ValueError):
        Outcome(kind="success", latency_ms=-1.0)
    ok = Outcome(kind="partial", score=0.5, note="half")
    assert ok.kind == "partial" and ok.score == 0.5


def test_outcome_defaults_observed_at_to_now():
    before = time.time()
    outcome = Outcome(kind="success")
    after = time.time()
    assert before <= outcome.observed_at <= after


def test_outcome_explicit_observed_at_kept():
    outcome = Outcome(kind="failure", observed_at=1234.5)
    assert outcome.observed_at == 1234.5


def test_outcome_roundtrip():
    outcome = Outcome(kind="success", score=0.9, note="n", latency_ms=12.0)
    clone = Outcome.from_dict(outcome.to_dict())
    assert clone == outcome


def test_outcome_from_dict_rejects_bad_data():
    with pytest.raises(ValueError):
        Outcome.from_dict({})
    with pytest.raises(ValueError):
        Outcome.from_dict({"kind": "bogus"})


def test_is_positive():
    assert Outcome(kind="success").is_positive()
    assert not Outcome(kind="failure").is_positive()
    assert Outcome(kind="partial", score=0.7).is_positive()
    assert not Outcome(kind="partial", score=0.2).is_positive()
    assert not Outcome(kind="partial").is_positive()


def test_attach_outcome():
    hist = DecisionHistory()
    episode = hist.record(_record())
    updated = hist.attach_outcome(
        episode.episode_id, Outcome(kind="success", score=0.95))
    assert updated.outcome is not None
    assert updated.outcome.kind == "success"
    assert updated.outcome.score == 0.95
    assert hist.get(episode.episode_id).outcome.kind == "success"


def test_attach_outcome_unknown_id():
    hist = DecisionHistory()
    with pytest.raises(MemoryError):
        hist.attach_outcome("nope", Outcome(kind="success"))


def test_attach_outcome_rejects_wrong_type():
    hist = DecisionHistory()
    episode = hist.record(_record())
    with pytest.raises(TypeError):
        hist.attach_outcome(episode.episode_id, {"kind": "success"})


def test_double_attach_requires_overwrite():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="failure"))
    with pytest.raises(MemoryError):
        hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    updated = hist.attach_outcome(
        episode.episode_id, Outcome(kind="success"), overwrite=True)
    assert updated.outcome.kind == "success"


def test_outcome_visible_to_queries():
    hist = DecisionHistory()
    good = hist.record(_record())
    bad = hist.record(_record())
    hist.attach_outcome(good.episode_id, Outcome(kind="success"))
    hist.attach_outcome(bad.episode_id, Outcome(kind="failure"))
    assert len(hist.find(MemoryQuery(has_outcome=True))) == 2
    assert len(hist.find(MemoryQuery(has_outcome=False))) == 0
    assert len(hist.find(MemoryQuery(outcome_kinds={"success"}))) == 1
    winners = hist.find(MemoryQuery(outcome_kinds={"success", "partial"}))
    assert [e.episode_id for e in winners] == [good.episode_id]


def test_outcome_survives_to_dict():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="partial",
                                                    score=0.4))
    d = hist.get(episode.episode_id).to_dict()
    assert d["outcome"]["kind"] == "partial"
    assert d["outcome"]["score"] == 0.4
