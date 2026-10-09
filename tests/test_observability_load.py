"""Slice 348 — observability load tests: the cost of watching."""

from __future__ import annotations

import pytest

from hugrgate.errors import MetricError, ObservabilityError
from hugrgate.observability import load as load_mod
from hugrgate.observability.load import (
    DEFAULT_BUDGET_P99_US,
    ObservabilityLoadHarness,
)


def test_load_run_measures_real_overhead():
    harness = ObservabilityLoadHarness(warmup=20)
    result = harness.run(n=200)
    assert result.n == 200
    # The instrumented path genuinely costs something...
    assert result.instrumented_p50_us > result.baseline_p50_us
    # ...but stays far inside the gate budget on any sane host.
    assert result.overhead_p99_us >= 0.0
    assert result.within_budget is True
    harness.assert_within_budget(result)
    d = result.to_dict()
    assert d["n"] == 200
    assert d["budget_p99_us"] == DEFAULT_BUDGET_P99_US


def test_load_gate_trips_on_impossible_budget():
    harness = ObservabilityLoadHarness(budget_p99_us=0.000001, warmup=5)
    result = harness.run(n=20)
    assert result.within_budget is False
    with pytest.raises(ObservabilityError, match="exceeds budget"):
        harness.assert_within_budget(result)


def test_load_harness_validates_inputs():
    with pytest.raises(MetricError):
        ObservabilityLoadHarness(budget_p99_us=0.0)
    with pytest.raises(MetricError):
        ObservabilityLoadHarness(warmup=-1)
    with pytest.raises(MetricError):
        ObservabilityLoadHarness().run(n=0)


def test_load_exports_stay_inside_contract():
    assert set(load_mod.__all__) == {
        "DEFAULT_BUDGET_P99_US", "LoadResult", "ObservabilityLoadHarness"}
