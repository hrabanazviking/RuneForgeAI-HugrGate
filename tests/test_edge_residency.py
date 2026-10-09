"""Slice 189 — edge model residency tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.edge.memory import MemoryInfo, MemoryManager, MemoryMode
from hugrgate.edge.residency import (
    ModelEntry,
    ResidencyError,
    ResidencyManager,
)

MEMINFO_2G = ("MemTotal:        2000000 kB\n"
              "MemAvailable:    1800000 kB\n")


def _mgr(budget: int = 1000, memory: MemoryManager | None = None,
         ) -> ResidencyManager:
    return ResidencyManager(ram_budget_bytes=budget, memory=memory)


def _reg(mgr: ResidencyManager, name: str, size: int,
         **kw) -> ModelEntry:
    entry = ModelEntry(name=name, size_bytes=size, **kw)
    mgr.register_model(entry)
    return entry


# --- catalog: success ------------------------------------------------------------

def test_register_and_pin():
    mgr = _mgr()
    _reg(mgr, "tiny", 100, pinned=True)
    assert mgr.status()["models"]["tiny"]["pinned"] is True
    mgr.unpin("tiny")
    assert mgr.status()["models"]["tiny"]["pinned"] is False


# --- catalog: failure --------------------------------------------------------------

def test_register_rejects_bad_entries():
    mgr = _mgr()
    with pytest.raises(ResidencyError, match="non-empty"):
        mgr.register_model(ModelEntry(name="  ", size_bytes=10))
    with pytest.raises(ResidencyError, match="must be > 0"):
        mgr.register_model(ModelEntry(name="x", size_bytes=0))
    with pytest.raises(ResidencyError, match="can never fit"):
        mgr.register_model(ModelEntry(name="huge", size_bytes=10**9))
    _reg(mgr, "a", 10)
    with pytest.raises(ResidencyError, match="already registered"):
        mgr.register_model(ModelEntry(name="a", size_bytes=10))
    with pytest.raises(ResidencyError, match="can only register"):
        mgr.register_model("nope")  # type: ignore[arg-type]
    with pytest.raises(ResidencyError, match="unknown model"):
        mgr.acquire("ghost")
    with pytest.raises(ResidencyError):
        ResidencyManager(ram_budget_bytes=0)


# --- acquire/release -----------------------------------------------------------------

def test_acquire_release_refcount():
    mgr = _mgr()
    _reg(mgr, "m", 400)
    e1 = mgr.acquire("m")
    e2 = mgr.acquire("m")
    assert e1.refcount == 2 and e2.refcount == 2
    assert mgr.status()["used_bytes"] == 400
    mgr.release("m")
    assert mgr.status()["models"]["m"]["refcount"] == 1
    mgr.release("m")
    assert mgr.resident_models() == ["m"]  # still resident, idle


def test_release_without_acquire_raises():
    mgr = _mgr()
    _reg(mgr, "m", 400)
    with pytest.raises(ResidencyError, match="not acquired"):
        mgr.release("m")
    mgr.acquire("m")
    mgr.release("m")
    with pytest.raises(ResidencyError, match="not acquired"):
        mgr.release("m")


def test_lru_eviction_makes_room():
    ticks = [0.0]
    mgr = ResidencyManager(ram_budget_bytes=1000,
                           clock=lambda: ticks[0])
    _reg(mgr, "a", 400)
    _reg(mgr, "b", 400)
    _reg(mgr, "c", 400)
    mgr.acquire("a")
    mgr.release("a")          # idle at t=0
    ticks[0] = 10.0
    mgr.acquire("b")
    mgr.release("b")          # idle at t=10
    mgr.acquire("c")          # needs 400; evicts LRU "a"
    assert mgr.resident_models() == ["b", "c"]
    assert mgr.status()["used_bytes"] == 800


def test_pinned_models_never_evicted():
    mgr = _mgr(1000)
    _reg(mgr, "keep", 600, pinned=True)
    _reg(mgr, "temp", 600)
    mgr.acquire("keep")
    mgr.release("keep")
    # "temp" needs 600, only 400 free, "keep" is pinned+idle but safe
    with pytest.raises(ResidencyError, match="no evictable model"):
        mgr.acquire("temp")
    assert mgr.resident_models() == ["keep"]


def test_in_use_models_not_evicted():
    mgr = _mgr(1000)
    _reg(mgr, "busy", 600)
    _reg(mgr, "new", 600)
    mgr.acquire("busy")  # refcount 1: not evictable
    with pytest.raises(ResidencyError, match="no evictable model"):
        mgr.acquire("new")


def test_evict_idle():
    mgr = _mgr(1000)
    _reg(mgr, "a", 300)
    _reg(mgr, "b", 300, pinned=True)
    mgr.acquire("a")
    mgr.release("a")
    mgr.acquire("b")
    mgr.release("b")
    assert mgr.evict_idle() == ["a"]
    assert mgr.resident_models() == ["b"]


# --- memory-mode reaction ----------------------------------------------------------------

def test_low_memory_sheds_idle_models():
    mem = MemoryManager(meminfo_text=MEMINFO_2G)
    mgr = _mgr(2000, memory=mem)
    _reg(mgr, "a", 500)
    _reg(mgr, "b", 500, pinned=True)
    mgr.acquire("a")
    mgr.release("a")
    mgr.acquire("b")
    mgr.release("b")
    assert mem.refresh(MemoryInfo(2 * 2**30, 100 * 2**20, False, False)) \
        is MemoryMode.CRITICAL
    assert mgr.resident_models() == ["b"]  # idle "a" shed, pinned "b" kept


def test_critical_mode_refuses_non_pinned_acquire():
    mem = MemoryManager(meminfo_text=MEMINFO_2G)
    mem.refresh(MemoryInfo(2 * 2**30, 100 * 2**20, False, False))
    assert mem.mode is MemoryMode.CRITICAL
    mgr = _mgr(2000, memory=mem)
    _reg(mgr, "plain", 500)
    _reg(mgr, "vip", 500, pinned=True)
    with pytest.raises(ResidencyError, match="memory critical"):
        mgr.acquire("plain")
    assert mgr.acquire("vip").resident is True


def test_recovery_does_not_auto_reload():
    mem = MemoryManager(meminfo_text=MEMINFO_2G)
    mgr = _mgr(2000, memory=mem)
    _reg(mgr, "a", 500)
    mgr.acquire("a")
    mgr.release("a")
    mem.refresh(MemoryInfo(2 * 2**30, 100 * 2**20, False, False))
    assert mgr.resident_models() == []
    mem.refresh(MemoryInfo(2 * 2**30, 1800000 * 1024, False, False))
    assert mem.mode is MemoryMode.STANDARD
    assert mgr.resident_models() == []  # on-demand only


def test_status_serializes():
    mgr = _mgr()
    _reg(mgr, "a", 100)
    mgr.acquire("a")
    json.dumps(mgr.status())
