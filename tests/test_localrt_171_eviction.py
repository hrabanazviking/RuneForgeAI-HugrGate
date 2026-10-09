"""Slice 171 — model eviction policy.

Unit tests for ``hugrgate.runtimes.eviction``.
"""

from __future__ import annotations

import time

import pytest

from hugrgate.errors import SpecError
from hugrgate.runtimes import FakeRuntime, ModelRef
from hugrgate.runtimes.eviction import (
    CompositePolicy,
    EvictionBudget,
    Evictor,
    LRUPolicy,
    MemoryPressurePolicy,
    TTLPolicy,
)
from hugrgate.runtimes.residency import ResidencyManager


def _rt(name: str) -> FakeRuntime:
    rt = FakeRuntime()
    rt.name = name
    return rt


def _resident(mgr: ResidencyManager, name: str,
              idle_s: float = 0.0, age_s: float = 0.0,
              hold_lease: bool = False):
    rt = _rt(name)
    lease = mgr.acquire(rt, ModelRef(runtime=name, path=f"/{name}.gguf"))
    if not hold_lease:
        lease.release()  # idle resident, no live users
    entry = mgr.resident(name)
    assert entry is not None
    # Backdate *after* release: release() refreshes last_used_at.
    entry.last_used_at = time.time() - idle_s
    entry.acquired_at = time.time() - age_s
    if hold_lease:
        return lease, rt
    return None, rt


# -- budget --------------------------------------------------------------------------

def test_budget_rejects_negative_max():
    with pytest.raises(SpecError):
        EvictionBudget(max_to_evict=-1)


def test_composite_needs_a_policy():
    with pytest.raises(SpecError):
        CompositePolicy()


def test_lru_rejects_negative_idle():
    with pytest.raises(SpecError):
        LRUPolicy(max_idle_s=-1.0)


# -- LRU -------------------------------------------------------------------------------

def test_lru_evicts_oldest_idle_first():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0)
    _resident(mgr, "b", idle_s=50.0)
    _resident(mgr, "c", idle_s=5.0)
    policy = LRUPolicy(max_idle_s=10.0)
    decisions = policy.select(list(mgr.snapshot().values()),
                              EvictionBudget())
    assert [d.runtime_name for d in decisions] == ["a", "b"]
    assert all(d.policy == "lru" for d in decisions)
    assert "idle" in decisions[0].reason


def test_lru_skips_fresh_entries():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=1.0)
    policy = LRUPolicy(max_idle_s=60.0)
    assert policy.select(list(mgr.snapshot().values()),
                         EvictionBudget()) == []


def test_lru_skips_in_use_by_default():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0, hold_lease=True)
    policy = LRUPolicy(max_idle_s=10.0)
    assert policy.select(list(mgr.snapshot().values()),
                         EvictionBudget()) == []


def test_lru_evict_in_use_opt_in():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0, hold_lease=True)
    policy = LRUPolicy(max_idle_s=10.0, evict_in_use=True)
    decisions = policy.select(list(mgr.snapshot().values()),
                              EvictionBudget())
    assert [d.runtime_name for d in decisions] == ["a"]


# -- TTL ---------------------------------------------------------------------------------

def test_ttl_evicts_old_entries():
    mgr = ResidencyManager()
    _resident(mgr, "a", age_s=7200.0)
    _resident(mgr, "b", age_s=60.0)
    policy = TTLPolicy(ttl_s=3600.0)
    decisions = policy.select(list(mgr.snapshot().values()),
                              EvictionBudget())
    assert [d.runtime_name for d in decisions] == ["a"]


# -- memory pressure ---------------------------------------------------------------------

def test_memory_pressure_rests_when_cool():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0)
    policy = MemoryPressurePolicy(high_watermark_bytes=10**9,
                                  used_bytes_fn=lambda: 10**6)
    assert not policy.under_pressure()
    assert policy.select(list(mgr.snapshot().values()),
                         EvictionBudget()) == []


def test_memory_pressure_nominates_lru_first():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0)
    _resident(mgr, "b", idle_s=50.0)
    used = {"bytes": 2 * 10**9}
    policy = MemoryPressurePolicy(high_watermark_bytes=10**9,
                                  used_bytes_fn=lambda: used["bytes"])
    assert policy.under_pressure()
    decisions = policy.select(list(mgr.snapshot().values()),
                              EvictionBudget())
    assert [d.runtime_name for d in decisions] == ["a", "b"]
    assert "watermark" in decisions[0].reason


# -- composite -----------------------------------------------------------------------------

def test_composite_unions_without_duplicates():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0, age_s=7200.0)
    _resident(mgr, "b", idle_s=100.0)
    policy = CompositePolicy(LRUPolicy(max_idle_s=10.0),
                             TTLPolicy(ttl_s=3600.0))
    decisions = policy.select(list(mgr.snapshot().values()),
                              EvictionBudget())
    assert [d.runtime_name for d in decisions] == ["a", "b"]
    # "a" was nominated by both; LRU (first policy) wins.
    assert decisions[0].policy == "lru"


# -- evictor ---------------------------------------------------------------------------------

def test_evictor_applies_policy_to_manager():
    mgr = ResidencyManager()
    _, rt_a = _resident(mgr, "a", idle_s=100.0)
    _resident(mgr, "b", idle_s=100.0)
    evictor = Evictor(mgr, LRUPolicy(max_idle_s=10.0))
    report = evictor.run(EvictionBudget(max_to_evict=1))
    assert [d.runtime_name for d in report.evicted] == ["a"]
    assert not mgr.is_resident("a")
    assert rt_a.info().model is None  # actually unloaded
    assert mgr.is_resident("b")
    d = report.to_dict()
    assert d["evicted"][0]["runtime"] == "a"
    assert d["evicted"][0]["policy"] == "lru"


def test_evictor_honors_protected():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0)
    _resident(mgr, "b", idle_s=100.0)
    evictor = Evictor(mgr, LRUPolicy(max_idle_s=10.0))
    report = evictor.run(EvictionBudget(protected=frozenset({"a"})))
    assert [d.runtime_name for d in report.evicted] == ["b"]
    assert report.skipped_protected == 1
    assert mgr.is_resident("a")


def test_evictor_reports_in_use_skips():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0, hold_lease=True)
    evictor = Evictor(mgr, LRUPolicy(max_idle_s=10.0))
    report = evictor.run()
    assert report.evicted == []
    assert report.skipped_in_use == 1
    assert mgr.is_resident("a")


def test_evictor_empty_manager():
    evictor = Evictor(ResidencyManager(), LRUPolicy(max_idle_s=1.0))
    report = evictor.run()
    assert report.evicted == []


def test_repeated_pressure_passes_converge():
    mgr = ResidencyManager()
    _resident(mgr, "a", idle_s=100.0)
    _resident(mgr, "b", idle_s=50.0)
    used = {"bytes": 2 * 10**9}
    policy = MemoryPressurePolicy(
        high_watermark_bytes=10**9,
        used_bytes_fn=lambda: used["bytes"])
    evictor = Evictor(mgr, policy)

    def fake_free():
        # Simulate: each eviction frees 0.75 GB.
        used["bytes"] -= int(0.75 * 10**9)

    passes = 0
    while policy.under_pressure() and passes < 5:
        report = evictor.run(EvictionBudget(max_to_evict=1))
        assert len(report.evicted) == 1
        fake_free()
        passes += 1
    assert not policy.under_pressure()
    assert passes == 2
