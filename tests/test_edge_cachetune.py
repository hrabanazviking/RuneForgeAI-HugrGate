"""Slice 190 — edge cache tuning tests."""

from __future__ import annotations

import json

import pytest

from hugrgate import DecisionPolicy, DecisionSpec
from hugrgate.edge.cachetune import (
    DEFAULT_ENTRY_BYTES,
    EdgeCache,
    EdgeCacheConfig,
    EdgeCacheError,
    cache_config_for_board,
    tune_cache,
)
from hugrgate.edge.memory import MemoryInfo, MemoryManager, MemoryMode
from hugrgate.edge.platform import pi_baseline
from hugrgate.result import DecisionResult

MEMINFO_8G = ("MemTotal:        8000000 kB\n"
              "MemAvailable:    7000000 kB\n")


MEMINFO_1G = ("MemTotal:        1000000 kB\n"
              "MemAvailable:     900000 kB\n")


def _result() -> DecisionResult:
    return DecisionResult(value="a", probability=0.9, backend="t")


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["a", "b"])


# --- tune_cache: success ------------------------------------------------------------

def test_tune_cache_derives_from_budget():
    mem = MemoryManager(meminfo_text=MEMINFO_8G)
    cfg = tune_cache(mem)
    assert isinstance(cfg, EdgeCacheConfig)
    # cache budget = 15% of 7 GiB; entries of 4 KiB -> clamped to MAX
    expected = min(100_000, int(7000000 * 1024 * 0.15) // DEFAULT_ENTRY_BYTES)
    assert cfg.max_size == expected
    assert cfg.ttl_seconds == 300.0
    assert cfg.memory_mode == "standard"
    json.dumps(cfg.to_dict())


def test_tune_cache_clamps_degenerate():
    mem = MemoryManager(meminfo_text=MEMINFO_8G)
    cfg = tune_cache(mem, entry_bytes_estimate=10**15)
    assert cfg.max_size == 16  # MIN_ENTRIES floor
    cfg2 = tune_cache(mem, entry_bytes_estimate=1)
    assert cfg2.max_size == 100_000  # MAX_ENTRIES ceiling


def test_tune_cache_ttl_shrinks_with_pressure():
    mem = MemoryManager(meminfo_text=MEMINFO_1G)
    std_cfg = tune_cache(mem, ttl_seconds=400.0)
    std = std_cfg.ttl_seconds
    assert std_cfg.max_size < 100_000  # below the clamp: shrink is visible
    mem.refresh(MemoryInfo(1 * 2**30, 512 * 2**20, False, False))
    assert mem.mode is MemoryMode.LOW
    low = tune_cache(mem, ttl_seconds=400.0)
    assert low.ttl_seconds == pytest.approx(std * 0.5)
    assert low.max_size < std_cfg.max_size


# --- tune_cache: failure --------------------------------------------------------------

@pytest.mark.parametrize("kwargs", [
    {"entry_bytes_estimate": 0},
    {"entry_bytes_estimate": -5},
    {"ttl_seconds": 0},
    {"ttl_seconds": -1.0},
])
def test_tune_cache_rejects_bad_inputs(kwargs):
    mem = MemoryManager(meminfo_text=MEMINFO_8G)
    with pytest.raises(EdgeCacheError):
        tune_cache(mem, **kwargs)


def test_config_rejects_degenerate():
    with pytest.raises(EdgeCacheError):
        EdgeCacheConfig(max_size=0, ttl_seconds=1.0,
                        entry_bytes_estimate=64, memory_mode="standard",
                        source="tuned")


# --- board baseline ---------------------------------------------------------------------

def test_cache_config_for_board():
    cfg = cache_config_for_board(pi_baseline("Raspberry Pi 5"))
    assert cfg.max_size == 2000
    assert cfg.source == "board-baseline"
    cfg3 = cache_config_for_board(pi_baseline("Raspberry Pi 3 Model B+"))
    assert cfg3.max_size == 250
    with pytest.raises(EdgeCacheError):
        cache_config_for_board(pi_baseline("Raspberry Pi 5"),
                               ttl_seconds=0)


# --- EdgeCache -----------------------------------------------------------------------------

def test_edge_cache_serves_and_retunes():
    mem = MemoryManager(meminfo_text=MEMINFO_8G)
    ec = EdgeCache(mem)
    policy, spec, state = DecisionPolicy(), _spec(), {"x": 1}
    assert ec.get(state, spec, policy) is None
    assert ec.put(state, spec, policy, _result()) is True
    assert ec.get(state, spec, policy) is not None
    before = ec.config.max_size
    # degrade memory -> cache rebuilds smaller
    mem.refresh(MemoryInfo(8 * 2**30, 100 * 2**20, False, False))
    assert mem.mode is MemoryMode.CRITICAL
    assert ec.config.max_size < before
    assert ec.config.memory_mode == "critical"
    # entries dropped on retune (RAM freed now, not migrated)
    assert ec.get(state, spec, policy) is None
    stats = ec.stats()
    assert stats["config"]["max_size"] == ec.config.max_size


def test_edge_cache_retune_idempotent_without_mode_change():
    mem = MemoryManager(meminfo_text=MEMINFO_8G)
    ec = EdgeCache(mem)
    cfg = ec.retune()
    assert cfg.max_size == ec.config.max_size
