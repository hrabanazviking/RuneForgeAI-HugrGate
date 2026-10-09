"""Slice 178 — low-RAM operating mode tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.memory import (
    CRITICAL_AVAILABLE_BYTES,
    LOW_AVAILABLE_BYTES,
    EdgeMemoryError,
    MemoryInfo,
    MemoryManager,
    MemoryMode,
)

MEMINFO_8G = (
    "MemTotal:        8059744 kB\n"
    "MemFree:         6020000 kB\n"
    "MemAvailable:    7000000 kB\n"
    "Buffers:           50000 kB\n"
    "Cached:           800000 kB\n"
)

MEMINFO_512M = (
    "MemTotal:         503452 kB\n"
    "MemFree:           60000 kB\n"
    "MemAvailable:     180000 kB\n"
    "Buffers:           5000 kB\n"
    "Cached:           40000 kB\n"
)

MEMINFO_ANCIENT = (  # no MemAvailable line
    "MemTotal:        1010000 kB\n"
    "MemFree:         200000 kB\n"
    "Buffers:          50000 kB\n"
    "Cached:          150000 kB\n"
)


# --- success ---------------------------------------------------------------

def test_probe_parses_meminfo():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    info = mgr.probe()
    assert info.total_bytes == 8059744 * 1024
    assert info.available_bytes == 7000000 * 1024
    assert info.live is False
    assert not info.cgroup_limited


def test_ancient_kernel_falls_back_to_free_buffers_cached():
    mgr = MemoryManager(meminfo_text=MEMINFO_ANCIENT)
    info = mgr.probe()
    assert info.available_bytes == (200000 + 50000 + 150000) * 1024


def test_cgroup_limit_caps_total():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G,
                        cgroup_limit_bytes=512 * 1024 * 1024)
    info = mgr.probe()
    assert info.total_bytes == 512 * 1024 * 1024
    assert info.cgroup_limited


def test_mode_derivation_boundaries():
    assert MemoryManager.mode_for(LOW_AVAILABLE_BYTES) is MemoryMode.STANDARD
    assert MemoryManager.mode_for(LOW_AVAILABLE_BYTES - 1) is MemoryMode.LOW
    # boundary semantics: `<` — exactly-at-threshold stays in the higher mode
    assert MemoryManager.mode_for(CRITICAL_AVAILABLE_BYTES) is MemoryMode.LOW
    assert (MemoryManager.mode_for(CRITICAL_AVAILABLE_BYTES - 1)
            is MemoryMode.CRITICAL)


def test_refresh_drives_mode_and_notifies_in_order():
    mgr = MemoryManager(meminfo_text=MEMINFO_512M)
    seen: list[tuple[str, str]] = []
    mgr.on_mode_change(lambda o, n: seen.append((o.value, n.value)))
    mgr.on_mode_change(lambda o, n: seen.append(("second", n.value)))
    assert mgr.refresh() is MemoryMode.CRITICAL
    assert mgr.mode is MemoryMode.CRITICAL
    assert seen == [("standard", "critical"), ("second", "critical")]
    # no change -> no notification
    assert mgr.refresh() is MemoryMode.CRITICAL
    assert len(seen) == 2


def test_budgets_shrink_as_mode_degrades():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    std_cache = mgr.budget_bytes("cache")
    mgr.refresh(MemoryInfo(8 * 2**30, 100 * 2**20, False, False))
    assert mgr.mode is MemoryMode.CRITICAL
    assert mgr.budget_bytes("cache") < std_cache
    assert mgr.budgets()["models"] > 0


def test_allocate_release_ledger():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    budget = mgr.budget_bytes("cache")
    mgr.allocate("cache", "a", budget // 2)
    mgr.allocate("cache", "b", budget // 2)
    assert mgr.ledger() == {"cache/a": budget // 2, "cache/b": budget // 2}
    assert mgr.release("cache", "a") == budget // 2
    assert mgr.release("cache", "missing") == 0


# --- failure -----------------------------------------------------------------

def test_allocate_over_budget_raises():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    with pytest.raises(EdgeMemoryError, match="over budget"):
        mgr.allocate("cache", "hog", mgr.budget_bytes("cache") + 1)


def test_allocate_unknown_component_raises():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    with pytest.raises(EdgeMemoryError, match="unknown memory component"):
        mgr.allocate("mystery", "x", 8)


def test_duplicate_allocation_raises():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    mgr.allocate("cache", "a", 8)
    with pytest.raises(EdgeMemoryError, match="duplicate allocation"):
        mgr.allocate("cache", "a", 8)


def test_negative_allocation_raises():
    mgr = MemoryManager(meminfo_text=MEMINFO_8G)
    with pytest.raises(EdgeMemoryError):
        mgr.allocate("cache", "neg", -1)


def test_probe_survives_missing_meminfo(monkeypatch):
    def boom(*a: object, **k: object) -> object:
        raise OSError("no /proc")
    monkeypatch.setattr("builtins.open", boom)
    info = MemoryManager().probe()
    assert info.total_bytes == 0 and info.available_bytes == 0


def test_live_manager_refresh_runs_on_this_host():
    mgr = MemoryManager()
    mode = mgr.refresh()
    assert isinstance(mode, MemoryMode)
