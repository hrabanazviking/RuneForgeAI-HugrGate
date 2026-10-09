"""Slice 259 — disk-full simulation tests."""

from __future__ import annotations

import errno

import pytest

from hugrgate.chaos import disk_full
from hugrgate.edge.storage import StorageError, WearAwareStore

# --- the simulation itself -------------------------------------------------------------------

def test_disk_full_blocks_writes_not_reads(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("readable")
    with disk_full():
        with pytest.raises(OSError) as exc:
            open(target, "w")
        assert exc.value.errno == errno.ENOSPC
        assert target.read_text() == "readable"  # reads pass through
        with pytest.raises(OSError):
            open(tmp_path / "new.bin", "wb")
        with pytest.raises(OSError):
            open(target, "r+b")
    # After the context, writes work again.
    target.write_text("writable again")
    assert target.read_text() == "writable again"


def test_disk_full_custom_errno(tmp_path):
    with disk_full(errno.EDQUOT):
        with pytest.raises(OSError) as exc:
            open(tmp_path / "q", "w")
        assert exc.value.errno == errno.EDQUOT


# --- WearAwareStore under a full disk ----------------------------------------------------------

def test_flush_maps_enospc_to_storage_error(tmp_path):
    store = WearAwareStore.open(tmp_path, write_budget_bytes=10**6)
    store.put("k", b"v")
    with disk_full():
        with pytest.raises(StorageError, match="disk full") as exc:
            store.flush()
    assert "buffer retained" in str(exc.value)
    assert exc.value.code == "edge_storage_error"
    # No torn temp file left behind.
    assert not list(tmp_path.glob("*.log.tmp"))
    # The buffered write survived: still readable from the buffer.
    assert store.get("k") == b"v"


def test_store_recovers_after_space_is_freed(tmp_path):
    store = WearAwareStore.open(tmp_path, write_budget_bytes=10**6)
    store.put("k", b"v")
    with disk_full():
        with pytest.raises(StorageError, match="disk full"):
            store.flush()
    # Space freed: the retained buffer flushes normally.
    assert store.flush() > 0
    assert store.get("k") == b"v"
    # And it survives a reopen from the log.
    store.close()
    reopened = WearAwareStore.open(tmp_path, write_budget_bytes=10**6)
    assert reopened.get("k") == b"v"
    reopened.close()


def test_non_enospc_oserror_still_maps_to_storage_error(tmp_path):
    store = WearAwareStore.open(tmp_path, write_budget_bytes=10**6)
    store.put("k", b"v")
    with disk_full(errno.EIO):
        with pytest.raises(StorageError, match=r"flush to .* failed"):
            store.flush()


def test_previously_flushed_data_survives_disk_full(tmp_path):
    store = WearAwareStore.open(tmp_path, write_budget_bytes=10**6)
    store.put("durable", b"yes")
    store.flush()
    store.put("pending", b"no-room")
    with disk_full():
        with pytest.raises(StorageError, match="disk full"):
            store.flush()
    # Durable data readable; pending data still buffered, not lost.
    assert store.get("durable") == b"yes"
    assert store.get("pending") == b"no-room"
    store._closed = True  # avoid close() flush outside the test scope
