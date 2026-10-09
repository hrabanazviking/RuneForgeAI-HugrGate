"""Slice 276 — profiler integration.

Covers: DecisionProfiler.profile / profile_decision (success, error
propagation, metadata attach + strict-privacy suppression), config
validation errors, ProfileReport.top/to_dict/to_markdown, and the nested
profile_region timers.
"""

from __future__ import annotations

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.errors import ProfilingError
from hugrgate.profiling import (
    DecisionProfiler,
    ProfileReport,
    profile_region,
    region_report,
)
from hugrgate.result import DecisionResult

pytestmark = pytest.mark.slow


class StubBackend(Backend):
    name = "stub-276"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        total = 0
        for i in range(2000):
            total += i  # busy work so the profiler sees real frames
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0,
                                            "b": 0.0})


def _gate() -> HugrGate:
    gate = HugrGate()
    gate.register(StubBackend())
    return gate


SPEC = DecisionSpec(type="categorical", options=["a", "b"])


# --- profile() ---------------------------------------------------------------

def test_profile_returns_result_and_report():
    profiler = DecisionProfiler()
    result, report = profiler.profile(
        _gate().decide, {"x": 1}, SPEC, label="decide")
    assert result.value == "a"
    assert isinstance(report, ProfileReport)
    assert report.wall_ms > 0
    assert report.total_calls > 0
    assert report.entries
    # the backend's evaluate must appear among the profiled frames
    assert any("evaluate" in e.function for e in report.entries)


def test_profile_propagates_callable_errors():
    profiler = DecisionProfiler()

    def boom():
        raise ValueError("kablam")

    with pytest.raises(ValueError, match="kablam"):
        profiler.profile(boom)


def test_profile_report_top_orders_by_cumtime():
    _, report = DecisionProfiler().profile(
        _gate().decide, {"x": 1}, SPEC)
    top = report.top(5)
    assert len(top) == 5
    cumtimes = [e.cumtime_ms for e in top]
    assert cumtimes == sorted(cumtimes, reverse=True)


def test_profile_report_top_rejects_bad_n():
    _, report = DecisionProfiler().profile(
        _gate().decide, {"x": 1}, SPEC)
    with pytest.raises(ProfilingError):
        report.top(0)


def test_profile_report_serializes():
    _, report = DecisionProfiler().profile(
        _gate().decide, {"x": 1}, SPEC, label="ser")
    d = report.to_dict()
    assert d["label"] == "ser"
    assert d["wall_ms"] > 0
    assert d["entries"][0]["function"]
    md = report.to_markdown(n=3)
    assert "## Profile: ser" in md
    assert md.count("|") >= 4


# --- config validation --------------------------------------------------------

@pytest.mark.parametrize("sort_by", ["bogus", "", "TOTAL"])
def test_bad_sort_key_rejected(sort_by):
    with pytest.raises(ProfilingError):
        DecisionProfiler(sort_by=sort_by)


@pytest.mark.parametrize("max_entries", [-1, "many", 1.5])
def test_bad_max_entries_rejected(max_entries):
    with pytest.raises(ProfilingError):
        DecisionProfiler(max_entries=max_entries)


# --- profile_decision ---------------------------------------------------------

def test_profile_decision_attaches_summary_to_metadata():
    profiler = DecisionProfiler()
    result, _ = profiler.profile_decision(_gate(), {"x": 1}, SPEC)
    summary = result.metadata["profile"]
    assert summary["wall_ms"] > 0
    assert summary["total_calls"] > 0
    assert len(summary["top"]) == 10
    assert all("function" in row and "cumtime_ms" in row
               for row in summary["top"])


def test_profile_decision_strict_privacy_withholds_summary():
    profiler = DecisionProfiler()
    policy = DecisionPolicy(minimum_probability=0.0, privacy_class="strict")
    result, report = profiler.profile_decision(
        _gate(), {"x": 1}, SPEC, policy=policy)
    assert "profile" not in result.metadata
    # the local report is still fully available to the caller
    assert report.entries


def test_profile_decision_opt_out_of_metadata():
    profiler = DecisionProfiler(attach_to_metadata=False)
    result, _ = profiler.profile_decision(_gate(), {"x": 1}, SPEC)
    assert "profile" not in result.metadata


def test_profile_decision_max_entries_trims():
    profiler = DecisionProfiler(max_entries=5)
    _, report = profiler.profile_decision(_gate(), {"x": 1}, SPEC)
    assert len(report.entries) <= 5


# --- profile_region -----------------------------------------------------------

def test_profile_region_nests_and_reports():
    region_report()  # reset
    with profile_region("outer"):
        with profile_region("inner"):
            pass
        with profile_region("inner"):
            pass
    report = region_report()
    assert report["outer"]["calls"] == 1
    assert report["inner"]["calls"] == 2
    assert report["outer"]["total_ms"] >= report["outer"]["own_ms"] >= 0
    assert report["inner"]["total_ms"] >= 0
    # reset consumed the totals
    assert region_report() == {}


def test_profile_region_rejects_empty_name():
    with pytest.raises(ProfilingError):
        with profile_region(""):
            pass


def test_profile_region_still_records_on_exception():
    region_report()
    with pytest.raises(RuntimeError):
        with profile_region("fragile"):
            raise RuntimeError("nope")
    assert region_report()["fragile"]["calls"] == 1
