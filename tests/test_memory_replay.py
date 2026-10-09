"""Slice 319 — Memory replay: re-run history through a policy function."""

from __future__ import annotations

import pytest

from hugrgate.memory import (
    DecisionHistory,
    MemoryQuery,
    ReplayReport,
    replay,
)
from hugrgate.provenance import DecisionRecord


def _record(**kw) -> DecisionRecord:
    base = dict(request_hash="h" * 16, spec={"type": "binary"},
                backend="local", model="m1", value=True, probability=0.8)
    base.update(kw)
    return DecisionRecord(**base)


def _history() -> DecisionHistory:
    hist = DecisionHistory()
    hist.record(_record(value=True, probability=0.8))
    hist.record(_record(value=False, probability=0.3))
    hist.record(_record(value=True, probability=0.9))
    return hist


def test_identical_policy_replays_clean():
    hist = _history()
    report = replay(hist, lambda spec: (True, 0.8))
    # only the value=False episode mismatches on value
    assert isinstance(report, ReplayReport)
    assert report.total == 3
    assert report.replayed == 3
    assert report.errors == 0
    assert report.value_matches == 2
    assert report.value_match_rate == pytest.approx(2 / 3)
    assert len(report.mismatches) == 1
    mismatch = report.mismatches[0]
    assert mismatch.recorded_value is False
    assert mismatch.replayed_value is True
    assert mismatch.value_match is False
    assert mismatch.prob_drift == pytest.approx(abs(0.3 - 0.8))


def test_prob_drift_statistics():
    hist = _history()
    report = replay(hist, lambda spec: (True, 0.5))
    assert report.mean_abs_prob_drift == pytest.approx(
        (0.3 + 0.2 + 0.4) / 3)


def test_decide_may_use_spec():
    hist = DecisionHistory()
    hist.record(_record(spec={"type": "binary", "statement": "go?"}))
    seen = []

    def decide(spec):
        seen.append(spec)
        return (spec.get("statement") == "go?", 1.0)

    report = replay(hist, decide)
    assert report.value_matches == 1
    assert seen[0]["type"] == "binary"


def test_decide_must_not_mutate_history():
    hist = _history()

    def evil(spec):
        spec["type"] = "corrupted"
        return (True, 0.5)

    replay(hist, evil)
    assert all(e.record.spec["type"] == "binary"
               for e in hist.recent(10))


def test_failing_decide_counted_not_fatal():
    hist = _history()

    def flaky(spec):
        raise RuntimeError("backend exploded")

    report = replay(hist, flaky)
    assert report.errors == 3
    assert report.replayed == 0
    assert len(report.error_episodes) == 3
    assert report.value_match_rate is None
    assert report.mean_abs_prob_drift is None


def test_bad_probability_type_counted():
    hist = _history()
    report = replay(hist, lambda spec: (True, "high"))  # type: ignore
    assert report.errors == 3
    assert report.replayed == 0


def test_query_prefilter_and_limit():
    hist = _history()
    report = replay(hist, lambda spec: (True, 0.8),
                    query=MemoryQuery(backends={"nope"}))
    assert report.total == 0
    assert report.replayed == 0
    report = replay(hist, lambda spec: (True, 0.8), limit=2)
    assert report.total == 2
    assert report.replayed == 2
    with pytest.raises(ValueError):
        replay(hist, lambda spec: (True, 0.8), limit=0)


def test_empty_history():
    report = replay(DecisionHistory(), lambda spec: (True, 0.5))
    assert report.total == 0
    assert report.value_match_rate is None
    assert report.to_dict()["errors"] == 0


def test_report_to_dict():
    report = replay(_history(), lambda spec: (True, 0.8))
    d = report.to_dict()
    assert d["total"] == 3
    assert d["value_match_rate"] == pytest.approx(2 / 3)
    assert len(d["mismatches"]) == 1
