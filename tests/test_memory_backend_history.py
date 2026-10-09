"""Slice 312 — Backend history features: per-backend track records."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    BackendHistory,
    DecisionHistory,
    MemoryQuery,
    Outcome,
    backend_histories,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8,
                latency_ms=10.0)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    for prob, kind in ((0.9, "success"), (0.7, "success"), (0.6, "failure")):
        episode = hist.record(_record(backend="local", probability=prob))
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    remote = hist.record(_record(backend="remote", model="m2",
                                 probability=0.4, accepted=False,
                                 latency_ms=0.0))
    hist.attach_outcome(remote.episode_id, Outcome(kind="failure"))
    hist.record(_record(backend="local", model="m3", probability=0.5))
    return hist


def test_backend_histories():
    hist = _history()
    now = time.time()
    table = backend_histories(hist, now=now)
    assert set(table) == {"local", "remote"}
    local = table["local"]
    assert isinstance(local, BackendHistory)
    assert local.decision_count == 4
    assert local.accepted_count == 4
    assert local.accepted_rate == 1.0
    assert local.outcome_counts == {"success": 2, "failure": 1}
    assert local.success_rate == pytest.approx(2 / 3)
    assert local.mean_probability == pytest.approx((0.9 + 0.7 + 0.6 + 0.5) / 4)
    assert local.decayed_mean_probability == pytest.approx(
        local.mean_probability, abs=0.05)
    assert local.mean_latency_ms == pytest.approx(10.0)
    assert local.first_seen <= local.last_seen
    assert local.models == ("m1", "m3")


def test_remote_backend():
    table = backend_histories(_history(), now=time.time())
    remote = table["remote"]
    assert remote.decision_count == 1
    assert remote.accepted_rate == 0.0
    assert remote.success_rate == 0.0
    assert remote.mean_latency_ms is None  # latency_ms=0.0 is not a sample


def test_success_rate_none_without_outcomes():
    hist = DecisionHistory()
    hist.record(_record(backend="local"))
    table = backend_histories(hist, now=time.time())
    assert table["local"].success_rate is None
    assert table["local"].outcome_counts == {}


def test_empty_history():
    assert backend_histories(DecisionHistory(), now=1.0) == {}


def test_query_prefilter():
    hist = _history()
    table = backend_histories(hist, query=MemoryQuery(accepted=True),
                              now=time.time())
    assert set(table) == {"local"}


def test_limit():
    hist = DecisionHistory()
    for _ in range(10):
        hist.record(_record(backend="local"))
    table = backend_histories(hist, limit=4, now=time.time())
    assert table["local"].decision_count == 4
    with pytest.raises(ValueError):
        backend_histories(hist, limit=0, now=time.time())


def test_to_dict():
    table = backend_histories(_history(), now=time.time())
    d = table["local"].to_dict()
    assert d["backend"] == "local"
    assert d["decision_count"] == 4
    assert d["models"] == ["m1", "m3"]
