"""Slice 260 — read-only filesystem tests."""

from __future__ import annotations

import errno

import pytest

from hugrgate.chaos import disk_full, read_only
from hugrgate.edge.recovery import CheckpointJournal
from hugrgate.edge.storage import StorageError, WearAwareStore
from hugrgate.errors import RecoveryError

# --- the simulation itself -------------------------------------------------------------------

def test_read_only_blocks_writes_not_reads(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("readable")
    with read_only():
        with pytest.raises(OSError) as exc:
            open(target, "w")
        assert exc.value.errno == errno.EROFS
        assert "Read-only" in exc.value.strerror
        assert target.read_text() == "readable"  # reads pass through
    target.write_text("writable again")


# --- WearAwareStore on a read-only filesystem ---------------------------------------------------

@pytest.fixture
def populated(tmp_path):
    store = WearAwareStore.open(tmp_path, write_budget_bytes=10**6)
    store.put("durable", b"yes")
    store.flush()
    store.close()
    return tmp_path


def test_reads_work_on_read_only_filesystem(populated):
    store = WearAwareStore.open(populated, write_budget_bytes=10**6)
    with read_only():
        assert store.get("durable") == b"yes"  # RAM index + log replay
        assert "durable" in store
    store._closed = True


def test_buffered_puts_work_but_flush_fails_loudly(populated):
    store = WearAwareStore.open(populated, write_budget_bytes=10**6)
    with read_only():
        store.put("pending", b"data")  # buffered in RAM: no disk touch
        assert store.get("pending") == b"data"
        with pytest.raises(StorageError) as exc_info:
            store.flush()  # EROFS is not ENOSPC: different message
        assert "disk full" not in str(exc_info.value).lower()
    store._closed = True


def test_close_with_pending_writes_fails_loudly_not_silently(populated):
    store = WearAwareStore.open(populated, write_budget_bytes=10**6)
    store.put("pending", b"data")
    with read_only():
        # close() must not swallow the failure and pretend the data
        # was persisted.
        with pytest.raises(StorageError):
            store.close()
    store._closed = True


def test_writes_resume_after_read_only_lifted(populated):
    store = WearAwareStore.open(populated, write_budget_bytes=10**6)
    store.put("blocked", b"data")
    with read_only():
        with pytest.raises(StorageError):
            store.flush()
    assert store.flush() > 0
    store.close()


# --- CheckpointJournal on failing disks ----------------------------------------------------------

def test_journal_checkpoint_maps_erofs_to_recovery_error(tmp_path):
    journal = CheckpointJournal.open(tmp_path)
    journal.checkpoint("s1", {"n": 1})
    with read_only():
        with pytest.raises(RecoveryError, match="read-only filesystem"):
            journal.checkpoint("s2", {"n": 2})
        # Reads still work; the good checkpoint is intact.
        assert journal.latest().payload == {"n": 1}
        assert not list(tmp_path.glob("*.json.tmp"))


def test_journal_checkpoint_maps_enospc_to_recovery_error(tmp_path):
    journal = CheckpointJournal.open(tmp_path)
    with disk_full():
        with pytest.raises(RecoveryError, match="disk full"):
            journal.checkpoint("s1", {"n": 1})
        assert not list(tmp_path.glob("*.json.tmp"))


def test_journal_recovers_after_disk_heals(tmp_path):
    journal = CheckpointJournal.open(tmp_path)
    journal.checkpoint("s1", {"n": 1})
    with disk_full():
        with pytest.raises(RecoveryError):
            journal.checkpoint("s2", {"n": 2})
    checkpoint = journal.checkpoint("s3", {"n": 3})
    assert checkpoint.state_id == "s3"
    assert journal.latest().payload == {"n": 3}
