"""Slice 456 — latency-budget tuner. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.latency import (
    LatencyBudgetTuner,
    empirical_tail,
    quantile,
)
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store():
    s = ConfigStore()
    for name in ("routing_ms", "backend_ms", "calib_ms"):
        s.register(TunableParameter(name=name, dtype="float", default=100.0,
                                    lo=1.0, hi=2000.0))
    return s


def _samples(seed=41):
    """backend is slow (mean ~400ms), routing/calib fast (~40/20ms)."""
    rng = seeded_rng(seed)
    return {
        "routing_ms": [rng.uniform(20, 60) for _ in range(500)],
        "backend_ms": [rng.uniform(200, 600) for _ in range(500)],
        "calib_ms": [rng.uniform(10, 30) for _ in range(500)],
    }


def test_quantile_and_tail():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert quantile(xs, 0.5) == pytest.approx(2.5)
    assert quantile(xs, 0.0) == 1.0
    assert quantile(xs, 1.0) == 4.0
    assert empirical_tail(xs, 2.5) == pytest.approx(0.5)
    with pytest.raises(TunerError):
        quantile([], 0.5)
    with pytest.raises(TunerError):
        empirical_tail([], 1.0)


def test_tuner_beats_equal_split_baseline():
    t = LatencyBudgetTuner(
        objective_id="overflow", stages=["routing_ms", "backend_ms",
                                         "calib_ms"],
        samples=_samples(), total_budget_ms=600.0, seed=2)
    prop = t.tune(_ctx(_store()))
    assert prop is not None
    ev = prop.evidence
    # The artifact: both numbers measured on the same samples.
    assert ev["tuned"]["joint_overflow"] < ev["baseline"]["joint_overflow"]
    assert prop.delta > 0  # negated overflow: higher is better
    # Budgets sum exactly to the total.
    assert sum(prop.changes.values()) == pytest.approx(600.0)
    # The slow stage gets the lion's share.
    assert prop.changes["backend_ms"] > prop.changes["calib_ms"]
    assert ev["n_samples"]["backend_ms"] == 500


def test_tuner_deterministic():
    kw = dict(objective_id="overflow",
              stages=["routing_ms", "backend_ms", "calib_ms"],
              samples=_samples(), total_budget_ms=600.0, seed=2)
    p1 = LatencyBudgetTuner(**kw).tune(_ctx(_store(), seed=9))
    p2 = LatencyBudgetTuner(**kw).tune(_ctx(_store(), seed=9))
    assert p1 is not None and p2 is not None
    assert p1.changes == p2.changes


def test_tuner_silent_when_equal_split_optimal():
    rng = seeded_rng(7)
    ident = {st: [rng.uniform(10, 50) for _ in range(300)]
             for st in ("a_ms", "b_ms")}
    s = ConfigStore()
    for st in ("a_ms", "b_ms"):
        s.register(TunableParameter(name=st, dtype="float", default=50.0,
                                    lo=1.0, hi=2000.0))
    t = LatencyBudgetTuner(objective_id="o", stages=["a_ms", "b_ms"],
                           samples=ident, total_budget_ms=200.0,
                           seed=2, min_delta=0.05)
    # identical stages: nothing beats equal split by 5 points
    assert t.tune(_ctx(s)) is None


def test_bad_specs_rejected():
    with pytest.raises(TunerError):
        LatencyBudgetTuner(objective_id="o", stages=["a"],
                           samples={"a": [1.0] * 30},
                           total_budget_ms=100.0, seed=1)
    with pytest.raises(TunerError):
        LatencyBudgetTuner(objective_id="o", stages=["a", "b"],
                           samples={"a": [1.0] * 30},  # b missing
                           total_budget_ms=100.0, seed=1)
    with pytest.raises(TunerError):
        LatencyBudgetTuner(objective_id="o", stages=["a", "b"],
                           samples={"a": [1.0] * 30, "b": [-5.0] * 30},
                           total_budget_ms=100.0, seed=1)
    with pytest.raises(TunerError):
        LatencyBudgetTuner(objective_id="o", stages=["a", "b"],
                           samples={"a": [1.0] * 30, "b": [2.0] * 30},
                           total_budget_ms=1.0, seed=1)  # below minimum


def test_non_float_stage_rejected():
    s = ConfigStore()
    s.register(TunableParameter(name="a_ms", dtype="int", default=5,
                                lo=1, hi=10))
    s.register(TunableParameter(name="b_ms", dtype="float", default=5.0,
                                lo=1.0, hi=10.0))
    t = LatencyBudgetTuner(objective_id="o", stages=["a_ms", "b_ms"],
                           samples={"a_ms": [1.0] * 30,
                                    "b_ms": [2.0] * 30},
                           total_budget_ms=100.0, seed=1)
    with pytest.raises(TunerError):
        t.tune(_ctx(s))


def test_end_to_end_offline():
    store = _store()
    c = OptimizationController(store=store)
    c.register_objective("overflow", lambda values: 0.0)
    c.register_tuner(LatencyBudgetTuner(
        objective_id="overflow",
        stages=["routing_ms", "backend_ms", "calib_ms"],
        samples=_samples(), total_budget_ms=600.0, seed=2))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("routing_ms") == 100.0  # offline: untouched
