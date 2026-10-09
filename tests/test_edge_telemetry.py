"""Slice 195 — edge telemetry lite tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.edge.telemetry import (
    TelemetryError,
    TelemetryLite,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1700000000.0
    def __call__(self) -> float:
        self.now += 0.5
        return self.now


# --- recording -----------------------------------------------------------------------

def test_record_and_recent_newest_first():
    tel = TelemetryLite(clock=Clock())
    e1 = tel.record("temp_c", 61.5, tags={"zone": "soc"})
    tel.record("temp_c", 62.0)
    assert e1.seq == 1
    recent = tel.recent()
    assert [e.seq for e in recent] == [2, 1]
    assert recent[1].to_dict()["tags"] == [["zone", "soc"]]
    assert tel.recent(1)[0].seq == 2


def test_ring_buffer_bounds_memory_and_counts_drops():
    tel = TelemetryLite(max_events=4)
    for i in range(10):
        tel.record("n", float(i))
    assert tel.stats()["buffered_events"] == 4
    assert tel.stats()["dropped_events"] == 6
    assert [e.value for e in tel.recent()] == [9.0, 8.0, 7.0, 6.0]


def test_counters_and_gauges():
    tel = TelemetryLite()
    assert tel.count("decisions") == 1.0
    assert tel.count("decisions", 4.0) == 5.0
    tel.gauge("temp_c", 70.25)
    tel.gauge("temp_c", 71.0)  # last value wins
    exported = tel.export()
    assert exported["counters"] == {"decisions": 5.0}
    assert exported["gauges"] == {"temp_c": 71.0}
    json.dumps(exported)


def test_reset_clears_but_keeps_seq():
    tel = TelemetryLite()
    tel.record("a", 1.0)
    tel.count("c")
    tel.reset()
    assert tel.stats()["buffered_events"] == 0
    assert tel.export()["counters"] == {}
    assert tel.record("b", 2.0).seq == 2  # seq not reset


# --- privacy: numeric-only ----------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "61.5", {"v": 1}, [1.0], None, True, float("nan"),
])
def test_record_rejects_non_numeric(bad):
    tel = TelemetryLite()
    with pytest.raises(TelemetryError, match=r"must (be numeric|not be NaN)"):
        tel.record("temp_c", bad)  # type: ignore[arg-type]


def test_rejects_non_string_tags():
    tel = TelemetryLite()
    with pytest.raises(TelemetryError, match="str -> str"):
        tel.record("t", 1.0, tags={"zone": 7})  # type: ignore[dict-item]
    with pytest.raises(TelemetryError, match="string mapping"):
        tel.record("t", 1.0, tags=["zone"])  # type: ignore[arg-type]


def test_rejects_empty_names():
    tel = TelemetryLite()
    with pytest.raises(TelemetryError, match="non-empty"):
        tel.record("  ", 1.0)
    with pytest.raises(TelemetryError, match="non-empty"):
        tel.count("")
    with pytest.raises(TelemetryError, match="non-empty"):
        tel.gauge("", 1.0)


def test_bad_construction_rejected():
    with pytest.raises(TelemetryError, match="max_events"):
        TelemetryLite(max_events=0)
