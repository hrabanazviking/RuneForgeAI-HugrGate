"""Slice 191 — flash-wear-aware storage tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hugrgate.edge.storage import StorageError, WearAwareStore


def _store(tmp_path: Path, **kw) -> WearAwareStore:
    kw.setdefault("write_budget_bytes", 10 * 1024 * 1024)
    return WearAwareStore.open(tmp_path / "store", **kw)


# --- round-trip -------------------------------------------------------------------------

def test_put_get_roundtrip(tmp_path: Path):
    with _store(tmp_path) as store:
        store.put("model", b"\x00\x01\x02")
        store.put("cfg", b"{}")
        assert store.get("model") == b"\x00\x01\x02"
        assert store.get("missing") is None
        assert "model" in store and "missing" not in store
        assert len(store) == 2
        store.flush()
    # reopen: index rebuilt from the log
    with _store(tmp_path) as store2:
        assert store2.get("model") == b"\x00\x01\x02"
        assert len(store2) == 2


def test_unflushed_put_visible_before_flush(tmp_path: Path):
    with _store(tmp_path, buffer_bytes=10**9) as store:
        store.put("k", b"v")
        assert store.get("k") == b"v"  # served from buffer
        assert store.wear_stats()["flush_count"] == 0


def test_delete_tombstones(tmp_path: Path):
    with _store(tmp_path) as store:
        store.put("k", b"v")
        store.flush()
        store.delete("k")
        store.flush()
        assert store.get("k") is None
        assert len(store) == 0
    with _store(tmp_path) as store2:
        assert store2.get("k") is None


def test_overwrite_keeps_latest(tmp_path: Path):
    with _store(tmp_path) as store:
        store.put("k", b"old")
        store.put("k", b"new")
        store.flush()
        assert store.get("k") == b"new"


def test_auto_flush_on_buffer_full(tmp_path: Path):
    with _store(tmp_path, buffer_bytes=64) as store:
        for i in range(20):
            store.put(f"k{i}", b"x" * 32)
        assert store.wear_stats()["flush_count"] >= 1
        assert store.get("k0") == b"x" * 32


def test_compact_reclaims_dead_records(tmp_path: Path):
    with _store(tmp_path) as store:
        for i in range(10):
            store.put(f"k{i}", b"y" * 100)
        store.flush()
        before = (tmp_path / "store" / "data.log").stat().st_size
        for i in range(9):
            store.delete(f"k{i}")
        written = store.compact()
        after = (tmp_path / "store" / "data.log").stat().st_size
        assert after < before
        assert written == after
        assert store.get("k9") == b"y" * 100
        assert len(store) == 1


def test_wear_stats_amplification(tmp_path: Path):
    with _store(tmp_path) as store:
        # one put per flush -> amplification > 1 (headers + magic)
        for i in range(3):
            store.put(f"k{i}", b"z" * 10)
            store.flush()
        stats = store.wear_stats()
        assert stats["write_amplification"] > 1.0
        assert stats["flush_count"] == 3
        assert stats["budget_remaining"] < stats["budget_bytes"]
        json.dumps(store.to_dict())


def test_coalescing_reduces_flushes(tmp_path: Path):
    with _store(tmp_path, buffer_bytes=10**9) as store:
        for i in range(50):
            store.put(f"k{i}", b"v")
        assert store.wear_stats()["flush_count"] == 0
        store.flush()
        assert store.wear_stats()["flush_count"] == 1


# --- failure ------------------------------------------------------------------------------

def test_budget_exhaustion_fails_closed(tmp_path: Path):
    # magic (8) + record (8 header + 1 key + 1 value) = 18 bytes > 10 budget
    store = _store(tmp_path, write_budget_bytes=10)
    try:
        store.put("k", b"v")  # buffered, not yet written
        with pytest.raises(StorageError, match="budget exhausted"):
            store.flush()
        # the buffered put is retained for a later flush with budget
        assert store.get("k") == b"v"
        assert store.wear_stats()["budget_remaining"] == 10
    finally:
        # bypass close()'s flush: the budget is deliberately exhausted
        store._closed = True


def test_compact_budget_exhaustion(tmp_path: Path):
    with _store(tmp_path, write_budget_bytes=10**6) as store:
        store.put("k", b"v")
        store.flush()
        store._budget = 1  # simulate a spent budget
        with pytest.raises(StorageError, match="budget exhausted"):
            store.compact()


def test_bad_keys_and_values_rejected(tmp_path: Path):
    with _store(tmp_path) as store:
        with pytest.raises(StorageError, match="non-empty"):
            store.put("", b"v")
        with pytest.raises(StorageError, match="non-empty"):
            store.get("")
        with pytest.raises(StorageError, match="must be bytes"):
            store.put("k", "not-bytes")  # type: ignore[arg-type]
        with pytest.raises(StorageError, match="exceeds max"):
            store.put("k", b"x" * (16 * 1024 * 1024 + 1))
        with pytest.raises(StorageError, match="too long"):
            store.put("k" * 2000, b"v")


def test_corrupt_log_rejected(tmp_path: Path):
    d = tmp_path / "store"
    d.mkdir()
    (d / "data.log").write_bytes(b"NOT-A-STORE")
    with pytest.raises(StorageError, match="not a HugrGate wear store"):
        WearAwareStore.open(d, write_budget_bytes=10**6)


def test_truncated_log_rejected(tmp_path: Path):
    d = tmp_path / "store"
    d.mkdir()
    (d / "data.log").write_bytes(b"HGWS0001\x04\x00")
    with pytest.raises(StorageError, match="truncated"):
        WearAwareStore.open(d, write_budget_bytes=10**6)


def test_write_after_close_rejected(tmp_path: Path):
    store = _store(tmp_path)
    store.close()
    store.close()  # idempotent
    with pytest.raises(StorageError, match="closed"):
        store.put("k", b"v")


def test_bad_construction_rejected(tmp_path: Path):
    with pytest.raises(StorageError):
        WearAwareStore.open(tmp_path / "s", write_budget_bytes=0)
    with pytest.raises(StorageError):
        WearAwareStore.open(tmp_path / "s", write_budget_bytes=100,
                            buffer_bytes=0)
