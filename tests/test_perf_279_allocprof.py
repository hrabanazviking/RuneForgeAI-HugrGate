"""Slice 279 — allocation profiling.

Covers: track() region diffs (real allocated bytes attributed to the
allocating frame), snapshot_report() heap census, profile_decision()
metadata attach + strict-privacy suppression, top() validation,
constructor validation, and misuse errors.
"""

from __future__ import annotations

import tracemalloc

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.allocprof import AllocationProfiler, AllocationReport
from hugrgate.backend import Backend
from hugrgate.errors import ProfilingError
from hugrgate.result import DecisionResult

pytestmark = pytest.mark.slow


def _allocate_a_lot():
    # Distinctive allocation site: a big list built in this frame.
    return [i * i for i in range(20000)]


def test_track_attributes_allocations_to_site():
    profiler = AllocationProfiler()
    with profiler.track("alloc") as tracked:
        kept = _allocate_a_lot()  # noqa: F841 - kept alive past the snapshot
    report = tracked.report
    assert isinstance(report, AllocationReport)
    assert report.delta_bytes > 100_000  # 20k ints is well over 100 KB
    top = report.top(3)
    assert top
    assert any("test_perf_279_allocprof" in s.location for s in top), (
        [s.location for s in top])
    assert not tracemalloc.is_tracing()  # profiler cleaned up


def test_track_report_serializes():
    profiler = AllocationProfiler()
    with profiler.track("ser") as tracked:
        _allocate_a_lot()
    d = tracked.report.to_dict()
    assert d["label"] == "ser"
    assert d["delta_bytes"] > 0
    assert d["sites"][0]["location"]
    md = tracked.report.to_markdown(n=2)
    assert "## Allocations: ser" in md


def test_top_rejects_bad_n():
    profiler = AllocationProfiler()
    with profiler.track() as tracked:
        pass
    with pytest.raises(ProfilingError):
        tracked.report.top(0)


def test_constructor_validation():
    with pytest.raises(ProfilingError):
        AllocationProfiler(nframes=0)
    with pytest.raises(ProfilingError):
        AllocationProfiler(nframes=512)
    with pytest.raises(ProfilingError):
        AllocationProfiler(top_n=-1)


def test_snapshot_without_tracing_rejected():
    profiler = AllocationProfiler()
    assert not tracemalloc.is_tracing()
    with pytest.raises(ProfilingError):
        profiler.snapshot_report()


def test_snapshot_report_census():
    profiler = AllocationProfiler()
    profiler.start()
    try:
        kept = _allocate_a_lot()  # noqa: F841 - kept alive for the census
        report = profiler.snapshot_report(label="census")
        assert report.after_bytes > 0
        assert report.sites
    finally:
        profiler.stop()


def test_start_stop_idempotent_and_polite():
    profiler = AllocationProfiler()
    profiler.start()
    profiler.start()  # second start is a no-op
    assert tracemalloc.is_tracing()
    profiler.stop()
    assert not tracemalloc.is_tracing()
    profiler.stop()  # no-op


def test_start_does_not_stop_foreign_tracing():
    tracemalloc.start(4)
    profiler = AllocationProfiler()
    try:
        profiler.start()
        assert tracemalloc.is_tracing()
        profiler.stop()
        # the profiler did not start it, so it must not stop it
        assert tracemalloc.is_tracing()
    finally:
        tracemalloc.stop()


class StubBackend(Backend):
    name = "stub-279"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0, "b": 0.0})


def _gate() -> HugrGate:
    gate = HugrGate()
    gate.register(StubBackend())
    return gate


SPEC = DecisionSpec(type="categorical", options=["a", "b"])


def test_profile_decision_attaches_aggregates():
    profiler = AllocationProfiler()
    result, report = profiler.profile_decision(_gate(), {"x": 1}, SPEC)
    assert result.value == "a"
    summary = result.metadata["allocations"]
    assert summary["after_bytes"] > 0
    assert isinstance(summary["delta_bytes"], int)
    assert len(summary["top_sites"]) <= 5
    assert report.delta_bytes == summary["delta_bytes"]


def test_profile_decision_strict_privacy_withholds_sites():
    profiler = AllocationProfiler()
    policy = DecisionPolicy(minimum_probability=0.0, privacy_class="strict")
    result, report = profiler.profile_decision(
        _gate(), {"x": 1}, SPEC, policy=policy)
    assert "allocations" not in result.metadata
    assert isinstance(report, AllocationReport)
