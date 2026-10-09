"""Slice 370 — Regression history.

Covers: append/reload round-trip, record filtering, series
ordering, latest(), regression detection (higher- and lower-better,
best vs median baselines, min_drop tolerance, no-history),
series_summary, prune, corrupt-line refusal, and finding
serialization.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import EvalError
from hugrgate.evlab import (
    HistoryStore,
    RegressionFinding,
    detect_regression,
    series_summary,
)
from hugrgate.evlab.api import RunRecord


def _record(run_id, accuracy, brier=0.1, dataset="ds", backend="stub",
            at="2026-10-09T12:00:00", sha="abc123"):
    return RunRecord(
        run_id=run_id,
        experiment_name="exp",
        seed=0,
        started_at=at,
        finished_at=at,
        elapsed_s=1.0,
        hugrgate_version="0.1.0",
        python_version="3.12",
        platform={"os": "linux"},
        dataset_name=dataset,
        dataset_version="1.0.0",
        dataset_fingerprint="fp",
        policy={},
        privacy_class="open",
        tags={},
        backends={backend: {"accuracy": accuracy,
                            "brier_score": brier}},
        n_items=10,
        git_sha=sha,
    )


def _store(tmp_path, values, **kw):
    store = HistoryStore(tmp_path / "history.jsonl")
    for i, acc in enumerate(values):
        store.append(_record(f"run-{i}", acc,
                             at=f"2026-10-09T12:00:{i:02d}", **kw))
    return store


# --- store mechanics -------------------------------------------------------------------

def test_append_reload_roundtrip(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_record("r1", 0.9))
    assert (tmp_path / "h.jsonl").exists()
    records = store.records()
    assert len(records) == 1
    assert records[0].run_id == "r1"
    assert records[0].backends["stub"]["accuracy"] == 0.9


def test_append_rejects_non_record(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    with pytest.raises(EvalError):
        store.append({"run_id": "x"})


def test_missing_file_is_empty(tmp_path):
    store = HistoryStore(tmp_path / "nope.jsonl")
    assert store.records() == []
    assert store.latest("ds", "stub") is None
    assert store.series("ds", "stub", "accuracy") == []


def test_filtering(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    store.append(_record("r1", 0.9, dataset="a"))
    store.append(_record("r2", 0.8, dataset="b"))
    store.append(_record("r3", 0.7, dataset="a", backend="other"))
    assert [r.run_id for r in store.records(dataset="a")] == ["r1", "r3"]
    assert [r.run_id for r in store.records(backend="stub")] == ["r1",
                                                                 "r2"]
    assert store.records(fingerprint="nope") == []
    assert store.latest("a", "stub").run_id == "r1"


def test_series_order_and_filtering(tmp_path):
    store = _store(tmp_path, [0.9, 0.8, 0.85])
    points = store.series("ds", "stub", "accuracy")
    assert [v for _, v in points] == [0.9, 0.8, 0.85]
    assert [t for t, _ in points] == sorted(t for t, _ in points)
    assert store.series("ds", "stub", "missing_metric") == []


def test_corrupt_line_refused(tmp_path):
    path = tmp_path / "h.jsonl"
    store = HistoryStore(path)
    store.append(_record("r1", 0.9))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("not json at all\n")
    with pytest.raises(EvalError) as ei:
        store.records()
    assert "line 2" in str(ei.value)


def test_prune(tmp_path):
    store = _store(tmp_path, [0.9, 0.8, 0.85, 0.7, 0.75])
    removed = store.prune(keep_last=2)
    assert removed == 3
    assert [r.run_id for r in store.records()] == ["run-3", "run-4"]
    assert store.prune(keep_last=5) == 0
    with pytest.raises(EvalError):
        store.prune(keep_last=0)


# --- regression detection -----------------------------------------------------------------

def test_regression_detected(tmp_path):
    store = _store(tmp_path, [0.90, 0.92, 0.91, 0.70])
    finding = detect_regression(store, "ds", "stub", "accuracy")
    assert finding is not None
    assert finding.current == pytest.approx(0.70)
    assert finding.baseline == pytest.approx(0.92)
    assert finding.drop == pytest.approx(0.22)
    assert finding.current_run_id == "run-3"
    assert finding.baseline_run_id == "run-1"
    assert finding.current_sha == "abc123"


def test_no_regression_when_improving(tmp_path):
    store = _store(tmp_path, [0.70, 0.80, 0.90])
    assert detect_regression(store, "ds", "stub", "accuracy") is None


def test_min_drop_tolerance(tmp_path):
    store = _store(tmp_path, [0.90, 0.895])
    assert detect_regression(store, "ds", "stub", "accuracy",
                             min_drop=0.02) is None
    finding = detect_regression(store, "ds", "stub", "accuracy",
                                min_drop=0.001)
    assert finding is not None


def test_lower_better_metric(tmp_path):
    store = HistoryStore(tmp_path / "h.jsonl")
    for i, brier in enumerate([0.10, 0.11, 0.30]):
        store.append(_record(f"run-{i}", 0.9, brier=brier,
                             at=f"2026-10-09T12:00:{i:02d}"))
    finding = detect_regression(store, "ds", "stub", "brier_score",
                                higher_better=False)
    assert finding is not None
    assert finding.drop == pytest.approx(0.20)
    # Higher-better view of the same brier series: no regression.
    assert detect_regression(store, "ds", "stub", "brier_score",
                             higher_better=True) is None


def test_median_baseline(tmp_path):
    store = _store(tmp_path, [0.95, 0.90, 0.90, 0.90, 0.90, 0.70])
    finding = detect_regression(store, "ds", "stub", "accuracy",
                                baseline="median")
    assert finding is not None
    assert finding.baseline == pytest.approx(0.90)
    with pytest.raises(EvalError):
        detect_regression(store, "ds", "stub", "accuracy",
                          baseline="bogus")


def test_no_history_no_regression(tmp_path):
    store = _store(tmp_path, [0.70])
    assert detect_regression(store, "ds", "stub", "accuracy") is None
    empty = HistoryStore(tmp_path / "empty.jsonl")
    assert detect_regression(empty, "ds", "stub", "accuracy") is None


def test_window_validation(tmp_path):
    store = _store(tmp_path, [0.9, 0.8])
    with pytest.raises(EvalError):
        detect_regression(store, "ds", "stub", "accuracy", window=0)
    with pytest.raises(EvalError):
        detect_regression(store, "ds", "stub", "accuracy",
                          min_drop=-1.0)


def test_current_param_without_appending(tmp_path):
    store = _store(tmp_path, [0.90, 0.92])
    current = _record("pending", 0.70,
                      at="2026-10-09T12:00:09")
    finding = detect_regression(store, "ds", "stub", "accuracy",
                                current=current)
    assert finding is not None
    assert finding.current_run_id == "pending"
    assert finding.baseline == pytest.approx(0.92)
    # The store itself is untouched.
    assert [r.run_id for r in store.records()] == ["run-0", "run-1"]
    # Unscored current: nothing to compare.
    blank = _record("blank", 0.70, at="2026-10-09T12:00:09")
    blank.backends = {"stub": {}}
    assert detect_regression(store, "ds", "stub", "accuracy",
                             current=blank) is None
    with pytest.raises(EvalError):
        detect_regression(store, "ds", "stub", "accuracy",
                          current={"run_id": "x"})


def test_finding_roundtrip(tmp_path):
    store = _store(tmp_path, [0.90, 0.70])
    finding = detect_regression(store, "ds", "stub", "accuracy")
    clone = RegressionFinding.from_dict(finding.to_dict())
    assert clone.to_dict() == finding.to_dict()


# --- series summary --------------------------------------------------------------------------

def test_series_summary(tmp_path):
    store = _store(tmp_path, [0.9, 0.8, 0.85])
    summary = series_summary(store, "ds", "stub", "accuracy")
    assert summary == {"n": 3, "first": 0.9, "last": 0.85,
                       "min": 0.8, "max": 0.9,
                       "delta": pytest.approx(-0.05)}
    empty = series_summary(store, "ds", "stub", "nope")
    assert empty["n"] == 0 and empty["last"] is None
