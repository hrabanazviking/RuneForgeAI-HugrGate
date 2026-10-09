"""Slice 323 — Memory adversarial tests: hostile inputs get caught."""

from __future__ import annotations

import time

import pytest

from hugrgate.memory import (
    DecisionHistory,
    GroundTruth,
    Outcome,
    scan,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def test_clean_history_no_findings():
    hist = DecisionHistory()
    now = time.time()
    for i in range(5):
        episode = hist.record(_record())
        hist._by_id[episode.episode_id].recorded_at = now - 3600 - i
        hist.attach_outcome(
            episode.episode_id,
            Outcome(kind="success", observed_at=now - 3000 - i * 100))
    report = scan(hist, now=now)
    assert report.findings == []
    assert not report.has_critical


def test_outcome_flooding_detected():
    hist = DecisionHistory()
    now = time.time()
    for _ in range(10):
        episode = hist.record(_record())
        hist.attach_outcome(episode.episode_id,
                            Outcome(kind="success", observed_at=now))
    report = scan(hist, now=now, outcome_flood_threshold=5,
                  outcome_flood_window_seconds=60.0)
    findings = report.by_detector("outcome_flooding")
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert report.has_critical
    assert "10 outcomes" in findings[0].detail


def test_chronology_violation_detected():
    hist = DecisionHistory()
    now = time.time()
    episode = hist.record(_record())
    hist._by_id[episode.episode_id].recorded_at = now
    hist.attach_outcome(episode.episode_id,
                        Outcome(kind="success", observed_at=now - 9999))
    report = scan(hist, now=now)
    findings = report.by_detector("chronology_violation")
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].episode_ids == (episode.episode_id,)
    assert report.has_critical


def test_duplicate_flood_detected():
    hist = DecisionHistory()
    for _ in range(8):
        hist.record(_record(request_hash="ab" * 8))
    hist.record(_record(request_hash="cd" * 8))
    report = scan(hist, now=time.time(), duplicate_threshold=5)
    findings = report.by_detector("duplicate_flood")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "8x" in findings[0].detail
    assert not report.has_critical


def test_timestamp_anomalies_detected():
    hist = DecisionHistory()
    now = time.time()
    future_ep = hist.record(_record())
    hist._by_id[future_ep.episode_id].recorded_at = now + 7200
    ancient_ep = hist.record(_record())
    hist._by_id[ancient_ep.episode_id].recorded_at = 1000000000.0
    report = scan(hist, now=now)
    findings = report.by_detector("timestamp_anomaly")
    assert len(findings) == 2
    assert all(f.severity == "warn" for f in findings)
    details = " ".join(f.detail for f in findings)
    assert "future" in details and "2020" in details


def test_label_conflicts_detected():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(episode.episode_id,
                             GroundTruth(label=False, source="audit"))
    report = scan(hist, now=time.time())
    findings = report.by_detector("label_conflict")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert findings[0].episode_ids == (episode.episode_id,)


def test_agreeing_labels_not_flagged():
    hist = DecisionHistory()
    episode = hist.record(_record())
    hist.attach_outcome(episode.episode_id, Outcome(kind="success"))
    hist.attach_ground_truth(episode.episode_id,
                             GroundTruth(label=True, source="audit"))
    report = scan(hist, now=time.time())
    assert report.by_detector("label_conflict") == []


def test_scan_validation():
    hist = DecisionHistory()
    with pytest.raises(ValueError):
        scan(hist, outcome_flood_window_seconds=0)
    with pytest.raises(ValueError):
        scan(hist, outcome_flood_threshold=0)
    with pytest.raises(ValueError):
        scan(hist, duplicate_threshold=0)
    with pytest.raises(ValueError):
        scan(hist, future_tolerance_seconds=-1)


def test_empty_history():
    report = scan(DecisionHistory(), now=time.time())
    assert report.findings == []
    assert report.to_dict()["has_critical"] is False


def test_finding_to_dict():
    hist = DecisionHistory()
    for _ in range(8):
        hist.record(_record(request_hash="ab" * 8))
    report = scan(hist, now=time.time(), duplicate_threshold=5)
    d = report.to_dict()
    assert d["has_critical"] is False
    assert d["findings"][0]["detector"] == "duplicate_flood"
    assert len(d["findings"][0]["episode_ids"]) == 8
