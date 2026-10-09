"""Slice 193 — intermittent-power recovery tests."""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from hugrgate.edge.recovery import (
    Checkpoint,
    CheckpointJournal,
    RecoveryError,
)


def _journal(tmp_path: Path, **kw) -> CheckpointJournal:
    return CheckpointJournal.open(tmp_path / "journal", **kw)


# --- writing / reading ---------------------------------------------------------------------

def test_checkpoint_roundtrip(tmp_path: Path):
    j = _journal(tmp_path)
    cp = j.checkpoint("batch-7", {"offset": 42, "items": ["a"]})
    assert isinstance(cp, Checkpoint)
    assert cp.seq == 1 and cp.state_id == "batch-7"
    latest = j.latest()
    assert latest is not None
    assert latest.payload == {"offset": 42, "items": ["a"]}
    assert j.recover() == {"offset": 42, "items": ["a"]}
    stats = j.stats()
    assert stats["valid_checkpoints"] == 1 and stats["latest_seq"] == 1
    json.dumps(stats)


def test_sequences_increase_and_latest_wins(tmp_path: Path):
    j = _journal(tmp_path)
    j.checkpoint("a", {"n": 1})
    j.checkpoint("b", {"n": 2})
    assert j.latest().state_id == "b"  # type: ignore[union-attr]
    # reopening continues the sequence (no seq reuse after a reboot)
    j2 = _journal(tmp_path)
    cp = j2.checkpoint("c", {"n": 3})
    assert cp.seq == 3


def test_keep_bound_prunes_old(tmp_path: Path):
    j = _journal(tmp_path, keep=2)
    for i in range(5):
        j.checkpoint(f"s{i}", {"n": i})
    assert len(j.checkpoints()) == 2
    assert j.latest().state_id == "s4"  # type: ignore[union-attr]


def test_empty_journal_recovers_none(tmp_path: Path):
    j = _journal(tmp_path)
    assert j.latest() is None
    assert j.recover() is None


def test_mark_complete_removes_state(tmp_path: Path):
    j = _journal(tmp_path)
    j.checkpoint("done", {"n": 1})
    j.checkpoint("todo", {"n": 2})
    assert j.mark_complete("done") == 1
    assert j.latest().state_id == "todo"  # type: ignore[union-attr]
    assert j.mark_complete("missing") == 0


# --- power-cut simulation -----------------------------------------------------------------------

def _torn_write(journal_dir: Path, seq: int = 99) -> None:
    # Simulate power dying mid-write: a truncated record file.
    body = {"magic": "HGCK0001", "seq": seq, "state_id": "torn",
            "payload": {"half": True}}
    blob = json.dumps(body, sort_keys=True).encode()
    record = json.dumps({"body": body, "crc32": zlib.crc32(blob)})
    (journal_dir / f"chk_{seq:08d}_torn.json").write_bytes(
        record.encode()[: len(record) // 2])


def test_torn_write_skipped_in_favor_of_previous_good(tmp_path: Path):
    d = tmp_path / "journal"
    j = _journal(tmp_path)
    j.checkpoint("good", {"n": 1})
    _torn_write(d)
    latest = j.latest()
    assert latest is not None and latest.state_id == "good"
    assert j.recover() == {"n": 1}


def test_bitflip_detected_by_crc(tmp_path: Path):
    d = tmp_path / "journal"
    j = _journal(tmp_path)
    j.checkpoint("good", {"n": 1})
    j.checkpoint("flipped", {"n": 2})
    # flip one byte in the newest record's payload region
    newest = sorted(d.glob("chk_*.json"))[-1]
    data = bytearray(newest.read_bytes())
    data[len(data) // 2] ^= 0xFF
    newest.write_bytes(bytes(data))
    latest = j.latest()
    assert latest is not None and latest.state_id == "good"


def test_alien_magic_rejected(tmp_path: Path):
    d = tmp_path / "journal"
    d.mkdir(parents=True, exist_ok=True)
    (d / "chk_00000001_alien.json").write_text(
        json.dumps({"body": {"magic": "NOPE"}, "crc32": 0}))
    j = CheckpointJournal.open(d)
    assert j.latest() is None


# --- failure -----------------------------------------------------------------------------------------

def test_bad_construction_and_inputs(tmp_path: Path):
    with pytest.raises(RecoveryError, match="keep"):
        CheckpointJournal(tmp_path, keep=0)
    j = _journal(tmp_path)
    with pytest.raises(RecoveryError, match="non-empty"):
        j.checkpoint("  ", {})
    with pytest.raises(RecoveryError, match="JSON-serializable"):
        j.checkpoint("s", {"bad": object()})


def test_checkpoint_repr_and_dict(tmp_path: Path):
    j = _journal(tmp_path)
    cp = j.checkpoint("s", {"n": 1})
    assert "seq=1" in repr(cp)
    assert cp.to_dict()["state_id"] == "s"
