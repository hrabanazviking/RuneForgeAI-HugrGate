"""Slice 162 — model capability probing.

Unit tests for ``hugrgate.runtimes.probe`` using FakeRuntime: full
passes, skips for unadvertised capabilities, recorded failures, and
load-cycle behavior.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import BackendError, HugrGateError
from hugrgate.runtimes import (
    CAP_GENERATE,
    FakeRuntime,
    GenerationOptions,
    GenerationResult,
    ModelRef,
)
from hugrgate.runtimes.probe import (
    PROBE_NAMES,
    CapabilityReport,
    probe_runtime,
)


def _ref() -> ModelRef:
    return ModelRef(runtime="fake", path="synthetic", format="unknown")


# -- happy path ----------------------------------------------------------------------

def test_probe_full_pass_on_fake_runtime():
    report = probe_runtime(FakeRuntime(), model=_ref())
    assert report.ok
    assert report.failed == 0
    assert report.skipped == 0
    assert report.passed == len(PROBE_NAMES)
    assert report.elapsed_s >= 0.0


def test_probe_without_model_skips_nothing_but_load_cycle():
    report = probe_runtime(FakeRuntime())
    assert report.ok
    load = report.by_name("load_cycle")
    assert load is not None and load.passed
    assert "no model given" in load.detail


def test_probe_subset_selection():
    report = probe_runtime(FakeRuntime(), probes=("generate",))
    assert [r.name for r in report.results] == ["generate"]
    assert report.ok


def test_probe_unknown_name_raises():
    with pytest.raises(HugrGateError, match="unknown probes"):
        probe_runtime(FakeRuntime(), probes=("teleport",))  # type: ignore[arg-type]


# -- skips ------------------------------------------------------------------------------

def test_unadvertised_capabilities_are_skipped_not_failed():
    rt = FakeRuntime(supports=frozenset({CAP_GENERATE}))
    report = probe_runtime(rt)
    assert report.failed == 0
    assert report.ok  # skips don't fail the report
    for name in ("embed", "classify", "tokenize"):
        result = report.by_name(name)
        assert result is not None and result.skipped
        assert "not advertised" in result.detail
    assert report.by_name("generate").passed  # type: ignore[union-attr]


# -- failures are recorded ------------------------------------------------------------------

class BrokenRuntime(FakeRuntime):
    name = "broken"

    def generate(self, prompt: str,
                 options: GenerationOptions | None = None
                 ) -> GenerationResult:
        raise BackendError("synthetic engine failure")


def test_failures_recorded_not_raised():
    report = probe_runtime(BrokenRuntime())
    assert not report.ok
    assert report.failed == 1
    gen = report.by_name("generate")
    assert gen is not None and not gen.passed and not gen.skipped
    assert "synthetic engine failure" in gen.detail
    # other probes still ran
    assert report.by_name("embed").passed  # type: ignore[union-attr]


def test_load_cycle_failure_recorded():
    class CantLoad(FakeRuntime):
        name = "cant-load"

        def load(self, model: ModelRef) -> None:
            raise BackendError("disk is lava")

    report = probe_runtime(CantLoad(), model=_ref())
    load = report.by_name("load_cycle")
    assert load is not None and not load.passed
    assert "disk is lava" in load.detail
    assert not report.ok


# -- report shape ------------------------------------------------------------------------------

def test_summary_and_to_dict():
    report = probe_runtime(FakeRuntime(), model=_ref())
    text = report.summary()
    assert "fake" in text and "passed" in text
    assert "[passed] generate" in text
    data = report.to_dict()
    assert data["runtime"] == "fake"
    assert data["ok"] is True
    assert data["passed"] == len(PROBE_NAMES)
    assert len(data["results"]) == len(PROBE_NAMES)
    first = data["results"][0]
    assert set(first) == {"name", "status", "latency_s", "detail"}


def test_report_ok_requires_at_least_one_pass():
    report = CapabilityReport(runtime="x", model=None, results=[])
    assert not report.ok
