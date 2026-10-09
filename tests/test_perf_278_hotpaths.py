"""Slice 278 — hot-path inventory.

Covers: aggregation across runs (sums, runs_seen), cumtime ranking with
a deliberately slow function on top, hot() threshold semantics and
boundary validation, invalid constructor args, serialization shape,
and an end-to-end inventory over a real gate.decide workload.
"""

from __future__ import annotations

import time

import pytest

from hugrgate import DecisionPolicy, DecisionSpec, HugrGate
from hugrgate.backend import Backend
from hugrgate.errors import ProfilingError
from hugrgate.hotpaths import HotFunction, HotPathCollector
from hugrgate.profiling import DecisionProfiler
from hugrgate.result import DecisionResult

pytestmark = pytest.mark.slow


def _slow_helper():
    time.sleep(0.01)


def _fast_helper():
    pass


def _workload():
    _slow_helper()
    _fast_helper()


def test_slow_function_ranks_first():
    inv = HotPathCollector(runs=3, label="rank").collect(_workload)
    ranked = inv.ranked()
    assert ranked, "inventory must not be empty"
    # _workload contains _slow_helper, so it owns the top cumtime slot;
    # the slow helper itself must be right behind it.
    assert ranked[0].function.endswith(":_workload")
    assert ranked[1].function.endswith(":_slow_helper"), (
        f"expected _slow_helper second, got {ranked[1].function}")
    assert ranked[1].cumtime_ms >= 25.0  # 3 runs x 10 ms
    # share is relative to summed cumtime across all profiled frames
    assert ranked[1].share > 0.25


def test_aggregation_sums_across_runs():
    inv = HotPathCollector(runs=4).collect(_workload)
    slow = next(f for f in inv.functions
                if f.function.endswith(":_slow_helper"))
    assert slow.runs_seen == 4
    assert slow.calls == 4
    assert slow.cumtime_ms >= 35.0


def test_hot_threshold_flags_only_hot_functions():
    inv = HotPathCollector(runs=2).collect(_workload)
    hot = inv.hot(threshold=0.05)
    assert hot
    assert all(f.share >= 0.05 for f in hot)
    names = {f.function for f in hot}
    assert any(n.endswith(":_slow_helper") for n in names)
    # everything flagged is a subset of the ranked list
    ranked_names = [f.function for f in inv.ranked()]
    assert [f.function for f in hot] == [
        n for n in ranked_names if n in names]


def test_hot_threshold_boundary_validation():
    inv = HotPathCollector(runs=1).collect(_workload)
    with pytest.raises(ProfilingError):
        inv.hot(threshold=0.0)
    with pytest.raises(ProfilingError):
        inv.hot(threshold=1.5)
    # threshold=1.0 is legal (flags nothing unless a function owns all time)
    assert isinstance(inv.hot(threshold=1.0), list)


def test_collector_rejects_bad_runs():
    with pytest.raises(ProfilingError):
        HotPathCollector(runs=0)
    with pytest.raises(ProfilingError):
        HotPathCollector(runs=-3)


def test_inventory_serialization_shape():
    inv = HotPathCollector(runs=2, label="ser").collect(_workload)
    d = inv.to_dict()
    assert d["runs"] == 2
    assert d["label"] == "ser"
    assert d["total_ms"] > 0
    first = d["functions"][0]
    assert {"function", "cumtime_ms", "share", "percall_ms"} <= set(first)
    md = inv.to_markdown(n=5)
    assert "## Hot-path inventory: ser" in md
    assert "_slow_helper" in md


def test_hot_function_percall_zero_calls():
    f = HotFunction(function="x", cumtime_ms=0.0, tottime_ms=0.0,
                    calls=0, runs_seen=0)
    assert f.percall_ms == 0.0


class StubBackend(Backend):
    name = "stub-278"

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        return DecisionResult(value="a", probability=1.0,
                              distribution={"a": 1.0, "b": 0.0})


def test_inventory_over_real_decide_workload():
    gate = HugrGate()
    gate.register(StubBackend())
    spec = DecisionSpec(type="categorical", options=["a", "b"])
    policy = DecisionPolicy(minimum_probability=0.0)

    def workload():
        for i in range(5):
            gate.decide({"x": i}, spec, policy)

    inv = HotPathCollector(
        DecisionProfiler(), runs=3, label="decide").collect(workload)
    assert inv.runs == 3
    assert inv.total_ms > 0
    # the decide frame itself must be among the inventoried functions
    assert any(f.function == "core:decide" for f in inv.functions)
    # hot set is non-empty at a permissive threshold
    assert inv.hot(threshold=0.01)
