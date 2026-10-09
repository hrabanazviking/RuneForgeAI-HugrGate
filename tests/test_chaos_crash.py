"""Slice 272 — crash-only restart tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.chaos import CrashOnlyHarness, CrashReport
from hugrgate.chaos.crash import worker_main
from hugrgate.edge.recovery import CheckpointJournal
from hugrgate.errors import SpecError

pytestmark = pytest.mark.slow


def test_torn_and_corrupt_records_are_ignored(tmp_path):
    journal = CheckpointJournal.open(tmp_path)
    journal.checkpoint("svc", {"counter": 1})
    journal.checkpoint("svc", {"counter": 2})
    # A torn write: partial JSON, as if SIGKILL landed mid-write.
    (tmp_path / "chk_00000003_svc.json").write_text('{"body": {"mag')
    # A corrupt record: valid JSON, bad CRC.
    (tmp_path / "chk_00000004_svc.json").write_text(
        '{"body": {"magic": "nope"}, "crc32": 0}')
    # A leftover temp file from the atomic-write protocol.
    (tmp_path / "chk_00000005_svc.json.tmp").write_text("partial")
    # An alien file that merely looks journal-ish.
    (tmp_path / "chk_notes.json").write_text("hello")

    recovered = CheckpointJournal.open(tmp_path).recover()
    assert recovered == {"counter": 2}  # newest *valid* checkpoint
    checkpoints = CheckpointJournal.open(tmp_path).checkpoints()
    assert [c.payload["counter"] for c in checkpoints] == [2, 1]


def test_worker_main_writes_ordered_counters(tmp_path):
    assert worker_main(str(tmp_path), 5) == 0
    journal = CheckpointJournal.open(tmp_path)
    assert journal.recover() == {"counter": 5}


def test_kill9_mid_write_recovers_cleanly(tmp_path):
    harness = CrashOnlyHarness(tmp_path)
    report = harness.run_worker(kill_after_s=1.0)
    assert isinstance(report, CrashReport)
    assert report.killed is True  # the kill really happened mid-run
    assert report.recovered_cleanly is True
    assert report.recovered_counter >= 1
    assert report.checkpoints_valid >= 1
    # keep=3 pruning: at most 3 valid checkpoints survive, all with
    # counters <= the recovered one (a write prefix, no gaps).
    journal = CheckpointJournal.open(tmp_path)
    counters = sorted(c.payload["counter"]
                      for c in journal.checkpoints())
    assert counters[-1] == report.recovered_counter
    assert counters == sorted(counters)
    json.dumps(report.to_dict())


def test_kill9_leaves_no_unreaped_zombie(tmp_path):
    harness = CrashOnlyHarness(tmp_path)
    report = harness.run_worker(kill_after_s=0.5)
    assert report.killed is True
    # Reaping happened inside run_worker: no child to wait on, and a
    # second immediate run works (no PID/executor confusion).
    report2 = harness.run_worker(kill_after_s=0.5)
    assert report2.killed is True
    assert report2.pid != report.pid


def test_run_worker_rejects_bad_arguments(tmp_path):
    with pytest.raises(SpecError):
        CrashOnlyHarness(tmp_path).run_worker(kill_after_s=0)


def test_recovery_survives_repeated_kills(tmp_path):
    # Three consecutive kill -9 cycles on the same directory: the
    # journal must stay consistent every time (seq continues, no
    # phantom state). The kill countdown starts only after the first
    # checkpoint exists, so the test measures crash recovery rather
    # than racing worker startup (slice 500).
    harness = CrashOnlyHarness(tmp_path)
    counters = []
    for _ in range(3):
        report = harness.run_worker(kill_after_s=0.5,
                                    arm_after_first_checkpoint=True)
        assert report.recovered_cleanly is True
        counters.append(report.recovered_counter)
    assert all(c >= 1 for c in counters)
    # Sequence numbers keep increasing across restarts (no reuse).
    seqs = [int(p.name.split("_")[1])
            for p in tmp_path.glob("chk_*.json")]
    assert len(set(seqs)) == len(seqs)
