"""Slice 310 — Frequency features: grouped raw + decay-weighted counts."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    DecisionHistory,
    MemoryQuery,
    Outcome,
    by_backend,
    by_backend_value,
    by_model,
    by_outcome_kind,
    count_by,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    for backend in ("local", "local", "remote"):
        episode = hist.record(_record(backend=backend))
        hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    lone = hist.record(_record(backend="remote", value=False))
    hist.attach_outcome(lone.episode_id, Outcome(kind="failure"))
    hist.record(_record(backend="local"))  # no outcome
    return hist


def test_count_by_backend():
    hist = _history()
    table = count_by(hist, by_backend, now=time.time())
    assert table.total == 5
    assert table.entries["local"].count == 3
    assert table.entries["remote"].count == 2
    assert table.entries["local"].decayed_count == pytest.approx(
        table.entries["local"].count, abs=0.01)
    assert table.entries["local"].outcome_counts == {"success": 2}
    assert table.entries["remote"].outcome_counts == {
        "success": 1, "failure": 1}
    assert table.decayed_total == pytest.approx(table.total, abs=0.05)


def test_decayed_counts_age():
    hist = DecisionHistory()
    old = hist.record(_record(backend="local"))
    hist._by_id[old.episode_id].recorded_at -= 10 * 86400
    hist.record(_record(backend="local"))
    table = count_by(hist, by_backend, half_life_seconds=86400.0,
                     now=time.time())
    entry = table.entries["local"]
    assert entry.count == 2
    assert entry.decayed_count == pytest.approx(1.0 + 2 ** -10, abs=1e-6)
    assert entry.first_seen < entry.last_seen


def test_key_functions():
    hist = _history()
    by_model_table = count_by(hist, by_model, now=time.time())
    assert set(by_model_table.entries) == {"local/m1", "remote/m1"}
    value_table = count_by(hist, by_backend_value, now=time.time())
    assert "remote=False" in value_table.entries
    outcome_table = count_by(hist, by_outcome_kind, now=time.time())
    assert outcome_table.entries["success"].count == 3
    assert outcome_table.entries["failure"].count == 1
    assert outcome_table.entries["unknown"].count == 1


def test_top():
    hist = _history()
    table = count_by(hist, by_backend, now=time.time())
    top = table.top(1)
    assert len(top) == 1
    assert top[0].key == "local"
    assert table.top(0) == []
    with pytest.raises(ValueError):
        table.top(-1)


def test_query_prefilter():
    hist = _history()
    table = count_by(hist, by_backend,
                     query=MemoryQuery(has_outcome=True), now=time.time())
    assert table.total == 4


def test_limit_caps_scan():
    hist = DecisionHistory()
    for _ in range(10):
        hist.record(_record(backend="local"))
    table = count_by(hist, by_backend, limit=3, now=time.time())
    assert table.total == 3


def test_limit_validation():
    hist = _history()
    with pytest.raises(ValueError):
        count_by(hist, by_backend, limit=0)


def test_bad_key_function():
    hist = _history()
    with pytest.raises(ValueError):
        count_by(hist, lambda episode: "", now=time.time())


def test_empty_history():
    table = count_by(DecisionHistory(), by_backend, now=1.0)
    assert table.total == 0
    assert table.entries == {}
    assert table.top(5) == []


def test_to_dict_roundtrip_shape():
    hist = _history()
    d = count_by(hist, by_backend, now=time.time()).to_dict()
    assert d["total"] == 5
    assert d["entries"]["local"]["count"] == 3
    assert d["entries"]["local"]["outcome_counts"] == {"success": 2}
