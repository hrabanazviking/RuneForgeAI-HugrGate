"""Slice 317 — Memory compaction: roll old episodes into summaries."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    CompactionSummary,
    DecisionHistory,
    GroundTruth,
    Outcome,
    compact,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _aged_history(now: float) -> DecisionHistory:
    hist = DecisionHistory()
    for i, kind in enumerate(("success", "success", "failure")):
        episode = hist.record(_record(backend="local" if i < 2 else "remote",
                                      probability=0.9 - 0.1 * i))
        hist._by_id[episode.episode_id].recorded_at = now - (10 + i) * 86400
        hist.attach_outcome(episode.episode_id, Outcome(kind=kind))
    young = hist.record(_record(probability=0.5))
    hist._by_id[young.episode_id].recorded_at = now - 3600
    return hist


def test_compact_rolls_up_old_episodes():
    now = time.time()
    hist = _aged_history(now)
    summary = compact(hist, older_than_seconds=7 * 86400, now=now)
    assert isinstance(summary, CompactionSummary)
    assert summary.episode_count == 3
    assert summary.backend_counts == {"local": 2, "remote": 1}
    assert summary.outcome_counts == {"success": 2, "failure": 1}
    assert summary.success_rate == pytest.approx(2 / 3)
    assert summary.mean_probability == pytest.approx((0.9 + 0.8 + 0.7) / 3)
    assert summary.privacy_class_counts == {"standard": 3}
    assert summary.window_start < summary.window_end
    assert len(summary.compacted_episode_ids) == 3
    # raw episodes are gone, the young one survives
    assert hist.count() == 1
    # summary is stored on the history
    stored = hist.compaction_summaries()
    assert len(stored) == 1
    assert stored[0].episode_count == 3


def test_compact_nothing_old_returns_none():
    hist = DecisionHistory()
    hist.record(_record())
    assert compact(hist, older_than_seconds=86400,
                   now=time.time()) is None
    assert hist.compaction_summaries() == []


def test_compact_keeps_ground_truth_by_default():
    now = time.time()
    hist = DecisionHistory()
    precious = hist.record(_record())
    hist._by_id[precious.episode_id].recorded_at = now - 30 * 86400
    hist.attach_ground_truth(precious.episode_id,
                             GroundTruth(label=True, source="audit"))
    summary = compact(hist, older_than_seconds=7 * 86400, now=now)
    assert summary is None  # the only old episode was spared
    assert hist.count() == 1


def test_compact_ground_truth_when_asked():
    now = time.time()
    hist = DecisionHistory()
    precious = hist.record(_record())
    hist._by_id[precious.episode_id].recorded_at = now - 30 * 86400
    hist.attach_ground_truth(precious.episode_id,
                             GroundTruth(label=True, source="audit"))
    summary = compact(hist, older_than_seconds=7 * 86400, now=now,
                      keep_with_ground_truth=False)
    assert summary is not None
    assert summary.episode_count == 1
    assert hist.count() == 0


def test_compact_validation():
    hist = DecisionHistory()
    with pytest.raises(ValueError):
        compact(hist, older_than_seconds=0)
    with pytest.raises(ValueError):
        compact(hist, older_than_seconds=-5)


def test_summary_roundtrip():
    now = time.time()
    hist = _aged_history(now)
    summary = compact(hist, older_than_seconds=7 * 86400, now=now)
    assert summary is not None
    clone = CompactionSummary.from_dict(summary.to_dict())
    assert clone == summary


def test_summary_from_dict_rejects_bad_data():
    with pytest.raises(ValueError):
        CompactionSummary.from_dict({})
    with pytest.raises(ValueError):
        CompactionSummary.from_dict({"window_start": 1.0})
    with pytest.raises(ValueError):
        CompactionSummary.from_dict("nope")


def test_add_summary_validation():
    hist = DecisionHistory()
    with pytest.raises(TypeError):
        hist.add_compaction_summary({"not": "a summary"})


def test_multiple_compactions_accumulate():
    now = time.time()
    hist = _aged_history(now)
    compact(hist, older_than_seconds=11.5 * 86400, now=now)
    assert hist.compaction_summaries()[0].episode_count == 1
    compact(hist, older_than_seconds=7 * 86400, now=now)
    assert len(hist.compaction_summaries()) == 2
    assert hist.count() == 1  # only the young episode remains
