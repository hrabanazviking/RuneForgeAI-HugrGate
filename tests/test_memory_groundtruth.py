"""Slice 304 — Ground-truth attachment: verified labels, supersede audit."""

from __future__ import annotations

import pytest

from hugrgate.errors import MemoryError
from hugrgate.memory import (
    DecisionHistory,
    GroundTruth,
    MemoryQuery,
    Outcome,
    outcome_agrees,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def test_ground_truth_validation():
    with pytest.raises(ValueError):
        GroundTruth(label=True, confidence=1.5)
    with pytest.raises(ValueError):
        GroundTruth(label=True, confidence=-0.1)
    with pytest.raises(ValueError):
        GroundTruth(label=True, source="   ")
    with pytest.raises(ValueError):
        GroundTruth(label=True, source="")
    truth = GroundTruth(label="success", source="audit-job-7")
    assert truth.confidence == 1.0
    assert truth.verified_at > 0


def test_ground_truth_roundtrip():
    truth = GroundTruth(label=False, confidence=0.8, source="reviewer",
                        note="mislabeled")
    clone = GroundTruth.from_dict(truth.to_dict())
    assert clone == truth


def test_ground_truth_from_dict_rejects_bad_data():
    with pytest.raises(ValueError):
        GroundTruth.from_dict({})
    with pytest.raises(ValueError):
        GroundTruth.from_dict({"label": True})
    with pytest.raises(ValueError):
        GroundTruth.from_dict({"source": "x"})


def test_attach_ground_truth():
    hist = DecisionHistory()
    episode = hist.record(_record())
    updated = hist.attach_ground_truth(
        episode.episode_id, GroundTruth(label=True, source="human"))
    assert updated.ground_truth is not None
    assert updated.ground_truth.label is True
    assert hist.get(episode.episode_id).ground_truth.source == "human"


def test_attach_ground_truth_unknown_id():
    hist = DecisionHistory()
    with pytest.raises(MemoryError):
        hist.attach_ground_truth("nope", GroundTruth(label=1, source="s"))


def test_attach_ground_truth_rejects_wrong_type():
    hist = DecisionHistory()
    episode = hist.record(_record())
    with pytest.raises(TypeError):
        hist.attach_ground_truth(episode.episode_id, {"label": True})


def test_ground_truth_immutable_without_supersede():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_ground_truth(
        episode.episode_id, GroundTruth(label=True, source="v1"))
    with pytest.raises(MemoryError):
        hist.attach_ground_truth(
            episode.episode_id, GroundTruth(label=False, source="v2"))
    # value unchanged
    assert hist.get(episode.episode_id).ground_truth.label is True


def test_supersede_keeps_audit_trail():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_ground_truth(
        episode.episode_id, GroundTruth(label=True, source="v1"))
    updated = hist.attach_ground_truth(
        episode.episode_id, GroundTruth(label=False, source="v2"),
        supersede=True)
    assert updated.ground_truth.label is False
    revisions = updated.annotations["ground_truth_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["label"] is True
    assert revisions[0]["source"] == "v1"


def test_ground_truth_queryable():
    hist = DecisionHistory()
    e1 = hist.record(_record())
    hist.record(_record())
    hist.attach_ground_truth(e1.episode_id,
                             GroundTruth(label="ok", source="s"))
    assert len(hist.find(MemoryQuery(has_ground_truth=True))) == 1
    assert len(hist.find(MemoryQuery(has_ground_truth=False))) == 1


def test_outcome_agrees():
    assert outcome_agrees(GroundTruth(label=True, source="s"),
                          Outcome(kind="success")) is True
    assert outcome_agrees(GroundTruth(label=False, source="s"),
                          Outcome(kind="success")) is False
    assert outcome_agrees(GroundTruth(label="failure", source="s"),
                          Outcome(kind="failure")) is True
    assert outcome_agrees(GroundTruth(label="partial", source="s"),
                          Outcome(kind="success")) is False
    # partial outcomes are not verdicts
    assert outcome_agrees(GroundTruth(label=True, source="s"),
                          Outcome(kind="partial")) is None
    # non-comparable labels
    assert outcome_agrees(GroundTruth(label=42, source="s"),
                          Outcome(kind="success")) is None
    assert outcome_agrees(GroundTruth(label="banana", source="s"),
                          Outcome(kind="failure")) is None


def test_consistency_report():
    hist = DecisionHistory()
    agree = hist.record(_record())
    clash = hist.record(_record())
    partial = hist.record(_record())
    hist.attach_outcome(agree.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(agree.episode_id,
                             GroundTruth(label=True, source="audit"))
    hist.attach_outcome(clash.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(clash.episode_id,
                             GroundTruth(label=False, source="audit"))
    hist.attach_outcome(partial.episode_id, Outcome(kind="partial"))
    hist.attach_ground_truth(partial.episode_id,
                             GroundTruth(label=False, source="audit"))
    report = hist.consistency_report()
    assert len(report) == 1
    entry = report[0]
    assert entry["episode_id"] == clash.episode_id
    assert entry["outcome_kind"] == "success"
    assert entry["truth_label"] is False
    assert entry["truth_source"] == "audit"


def test_consistency_report_empty_history():
    assert DecisionHistory().consistency_report() == []
