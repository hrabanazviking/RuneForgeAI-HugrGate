"""Slice 318 — Memory export/import: JSONL backup and restore."""

from __future__ import annotations

import json

import pytest

from hugrgate.errors import MemoryError
from hugrgate.memory import (
    DecisionHistory,
    Episode,
    GroundTruth,
    MemoryQuery,
    Outcome,
    compact,
    export_jsonl,
    import_jsonl,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    e1 = hist.record(_record(), privacy_class="sensitive", tags=["a"])
    hist.attach_outcome(e1.episode_id, Outcome(kind="success", score=0.9))
    hist.attach_ground_truth(e1.episode_id,
                             GroundTruth(label=True, source="audit"))
    hist.record(_record(backend="remote"))
    return hist


def test_roundtrip(tmp_path):
    hist = _history()
    path = tmp_path / "memory.jsonl"
    report = export_jsonl(hist, path)
    assert report.episodes == 2
    assert report.bytes > 0
    assert path.exists()

    restored = DecisionHistory()
    incoming = import_jsonl(restored, path)
    assert incoming.imported == 2
    assert incoming.skipped_bad == 0
    assert incoming.skipped_duplicates == 0
    assert restored.count() == 2
    episodes = restored.find(MemoryQuery(privacy_classes={"sensitive"}))
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.outcome is not None and episode.outcome.kind == "success"
    assert episode.outcome.score == 0.9
    assert episode.ground_truth is not None
    assert episode.ground_truth.label is True
    assert episode.tags == ("a",)
    assert episode.privacy_class == "sensitive"
    # original ids preserved
    assert {e.episode_id for e in restored.recent(10)} == \
        {e.episode_id for e in hist.recent(10)}


def test_export_includes_summaries(tmp_path):
    import time
    hist = DecisionHistory()
    old = hist.record(_record())
    hist._by_id[old.episode_id].recorded_at -= 30 * 86400
    compact(hist, older_than_seconds=7 * 86400, now=time.time())
    assert len(hist.compaction_summaries()) == 1
    path = tmp_path / "m.jsonl"
    report = export_jsonl(hist, path)
    assert report.summaries == 1
    restored = DecisionHistory()
    incoming = import_jsonl(restored, path)
    assert incoming.summaries_imported == 1
    assert len(restored.compaction_summaries()) == 1
    assert restored.compaction_summaries()[0].episode_count == 1


def test_duplicate_import_skipped(tmp_path):
    hist = _history()
    path = tmp_path / "m.jsonl"
    export_jsonl(hist, path)
    incoming = import_jsonl(hist, path)  # same history: all duplicates
    assert incoming.imported == 0
    assert incoming.skipped_duplicates == 2
    assert hist.count() == 2


def test_corrupt_lines_skipped_with_report(tmp_path):
    hist = _history()
    path = tmp_path / "m.jsonl"
    export_jsonl(hist, path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
        fh.write('{"schema": "hugrgate.memory/episode", "version": 1}\n')
        fh.write(json.dumps({"schema": "nope", "version": 1,
                             "payload": {}}) + "\n")
        fh.write(json.dumps({"schema": "hugrgate.memory/episode",
                             "version": 999, "payload": {}}) + "\n")
    restored = DecisionHistory()
    incoming = import_jsonl(restored, path)
    assert incoming.imported == 2
    assert incoming.skipped_bad == 4
    assert len(incoming.errors) == 4
    assert restored.count() == 2


def test_strict_mode_raises(tmp_path):
    path = tmp_path / "m.jsonl"
    path.write_text("garbage\n", encoding="utf-8")
    with pytest.raises(MemoryError):
        import_jsonl(DecisionHistory(), path, skip_bad_lines=False)


def test_missing_file_raises():
    with pytest.raises(MemoryError):
        import_jsonl(DecisionHistory(), "/no/such/file.jsonl")


def test_import_episode_duplicate():
    hist = _history()
    episode = hist.recent(1)[0]
    with pytest.raises(MemoryError):
        hist.import_episode(episode)
    with pytest.raises(TypeError):
        hist.import_episode({"not": "an episode"})


def test_episode_from_dict_rejects_bad_data():
    with pytest.raises(ValueError):
        Episode.from_dict({})
    with pytest.raises(ValueError):
        Episode.from_dict({"episode_id": "x"})
    with pytest.raises(ValueError):
        Episode.from_dict("nope")


def test_export_report_to_dict(tmp_path):
    hist = _history()
    path = tmp_path / "m.jsonl"
    report = export_jsonl(hist, path)
    d = report.to_dict()
    assert d["episodes"] == 2
    assert d["bytes"] > 0
    incoming = import_jsonl(DecisionHistory(), path)
    assert incoming.to_dict()["imported"] == 2
