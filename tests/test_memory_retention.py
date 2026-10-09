"""Slice 316 — Memory retention controls: TTL, count, and byte quotas."""

from __future__ import annotations

import time

import pytest

from hugrgate.errors import MemoryQuotaExceeded
from hugrgate.memory import (
    DecisionHistory,
    MemoryQuota,
    check_quota,
    enforce_quotas,
)
from hugrgate.provenance import DecisionRecord, ProvenanceStore


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def test_quota_validation():
    with pytest.raises(ValueError):
        MemoryQuota(max_episodes=0)
    with pytest.raises(ValueError):
        MemoryQuota(max_bytes=0)
    with pytest.raises(ValueError):
        MemoryQuota(max_bytes=100, warn_bytes=200)


def test_max_age_for_defaults():
    quota = MemoryQuota()
    assert quota.max_age_for("standard") == 30 * 24 * 3600
    assert quota.max_age_for("forbidden") == 0
    assert quota.max_age_for("public") is None


def test_max_age_for_overrides():
    quota = MemoryQuota(ttl_overrides={"standard": 60.0})
    assert quota.max_age_for("standard") == 60.0
    assert quota.max_age_for("sensitive") == 7 * 24 * 3600


def test_ttl_purge():
    hist = DecisionHistory()
    now = time.time()
    old = hist.record(_record(), privacy_class="standard")
    hist._by_id[old.episode_id].recorded_at = now - 31 * 24 * 3600
    fresh = hist.record(_record(), privacy_class="standard")
    assert fresh is not None
    report = enforce_quotas(hist, MemoryQuota(), now=now)
    assert report.ttl_purged == 1
    assert hist.count() == 1
    assert report.episodes_before == 2
    assert report.episodes_after == 1


def test_forbidden_purged_immediately():
    hist = DecisionHistory()
    hist.record(_record(), privacy_class="forbidden")
    report = enforce_quotas(hist, MemoryQuota(), now=time.time())
    assert report.ttl_purged == 1
    assert hist.count() == 0


def test_count_quota_evicts_oldest_first():
    hist = DecisionHistory()
    ids = [hist.record(_record()).episode_id for _ in range(5)]
    report = enforce_quotas(hist, MemoryQuota(max_episodes=3),
                            now=time.time())
    assert report.count_evicted == 2
    assert hist.count() == 3
    remaining = [e.episode_id for e in hist.recent(10)]
    assert remaining == ids[2:]


def test_byte_quota_evicts_oldest_first():
    hist = DecisionHistory()
    ids = [hist.record(_record()).episode_id for _ in range(4)]
    one = hist.estimate_bytes() // 4
    report = enforce_quotas(hist, MemoryQuota(max_bytes=2 * one + 100),
                            now=time.time())
    assert hist.estimate_bytes() <= 2 * one + 100
    assert report.bytes_evicted >= 1
    remaining = {e.episode_id for e in hist.recent(10)}
    assert ids[0] not in remaining  # oldest went first


def test_unsatisfiable_byte_quota_raises():
    hist = DecisionHistory()
    hist.record(_record())
    single = hist.estimate_bytes()
    assert single > 0
    with pytest.raises(MemoryQuotaExceeded):
        enforce_quotas(hist, MemoryQuota(max_bytes=single // 2),
                       now=time.time())


def test_check_quota_statuses():
    hist = DecisionHistory()
    for _ in range(3):
        hist.record(_record())
    assert check_quota(hist, MemoryQuota()).status == "ok"
    assert check_quota(hist, MemoryQuota(max_episodes=2)).status == "over"
    n_bytes = hist.estimate_bytes()
    assert check_quota(hist, MemoryQuota(max_bytes=n_bytes - 1)).status \
        == "over"
    assert check_quota(hist, MemoryQuota(warn_bytes=n_bytes - 1)).status \
        == "warn"
    assert check_quota(hist, MemoryQuota(warn_bytes=n_bytes + 1)).status \
        == "ok"


def test_history_purge_primitive():
    hist = DecisionHistory()
    hist.record(_record(backend="local"))
    hist.record(_record(backend="remote"))
    removed = hist.purge(lambda e: e.record.backend == "remote")
    assert removed == 1
    assert hist.count() == 1
    assert hist.purge(lambda e: False) == 0


def test_provenance_estimate_bytes():
    store = ProvenanceStore()
    assert store.estimate_bytes() == 0
    store.append(_record())
    first = store.estimate_bytes()
    assert first > 0
    store.append(_record())
    assert store.estimate_bytes() > first


def test_report_to_dict():
    report = enforce_quotas(DecisionHistory(), MemoryQuota(),
                            now=time.time())
    d = report.to_dict()
    assert d["episodes_before"] == 0
    assert d["ttl_purged"] == 0
