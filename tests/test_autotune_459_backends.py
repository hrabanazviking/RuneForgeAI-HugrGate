"""Slice 459 — backend-order tuner. Unit tests."""

from __future__ import annotations

import itertools

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    OptimizationController,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.tuners._base import seeded_rng
from hugrgate.autotune.tuners.backends import (
    BackendOrderTuner,
    expected_chain_cost,
)
from hugrgate.errors import TunerError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="r")


def _store(backends, ranks=None):
    s = ConfigStore()
    for i, b in enumerate(backends):
        r = ranks[i] if ranks else i
        s.register(TunableParameter(name=f"backend.rank.{b}", dtype="int",
                                    default=r, lo=0, hi=len(backends) - 1))
    return s


STATS = {
    # name: (success_rate, cost). "cheap-flaky" looks good but its
    # cost-per-success (10/0.5=20) loses to "pricey-solid" (15/0.99~=15.2).
    "cheap-flaky": (0.5, 10.0),
    "pricey-solid": (0.99, 15.0),
    "mid": (0.8, 12.0),
}


def _tuner(**kw):
    base = dict(objective_id="cost", backends=list(STATS),
                stats=dict(STATS), seed=1)
    base.update(kw)
    return BackendOrderTuner(**base)


def test_expected_chain_cost():
    stats = {"a": (1.0, 5.0), "b": (1.0, 7.0)}
    assert expected_chain_cost(["a", "b"], stats) == pytest.approx(5.0)
    stats = {"a": (0.5, 5.0), "b": (1.0, 7.0)}
    assert expected_chain_cost(["a", "b"], stats) == pytest.approx(8.5)


def test_optimal_order_not_cheapest_first():
    t = _tuner()
    prop = t.tune(_ctx(_store(list(STATS))))
    assert prop is not None
    order = prop.evidence["tuned"]["order"]
    # cost/success: pricey-solid 15.15 < mid 15.0? recompute:
    # mid: 12/0.8 = 15.0 < pricey-solid 15.15 < cheap-flaky 20.0
    assert order == ["mid", "pricey-solid", "cheap-flaky"]
    assert prop.evidence["tuned"]["expected_cost"] < \
        prop.evidence["baseline"]["expected_cost"]


def test_matches_brute_force_on_random_instances():
    """The interchange-optimal order must equal exhaustive search."""
    rng = seeded_rng(77)
    for trial in range(30):
        names = [f"b{i}" for i in range(4)]
        stats = {n: (rng.uniform(0.2, 1.0), rng.uniform(1.0, 50.0))
                 for n in names}
        t = BackendOrderTuner(objective_id="o", backends=names,
                              stats=stats, seed=trial)
        # find a strictly-suboptimal start order (a random scramble
        # can be optimal by luck)
        prop = None
        for attempt in range(24):
            scrambled = list(names)
            srng = seeded_rng(1000 + trial * 100 + attempt)
            srng.shuffle(scrambled)
            ranks = [scrambled.index(n) for n in names]
            ctx = _ctx(_store(names, ranks=ranks), seed=trial)
            prop = t.tune(ctx)
            if prop is not None:
                break
        assert prop is not None, f"no suboptimal scramble found (trial {trial})"
        tuned_cost = expected_chain_cost(prop.evidence["tuned"]["order"],
                                         stats)
        brute = min(expected_chain_cost(list(p), stats)
                    for p in itertools.permutations(names))
        assert tuned_cost == pytest.approx(brute)


def test_silent_when_already_optimal():
    t = _tuner()
    first = t.tune(_ctx(_store(list(STATS))))
    assert first is not None
    order = first.evidence["tuned"]["order"]
    ranks = [order.index(b) for b in STATS]
    assert t.tune(_ctx(_store(list(STATS), ranks=ranks))) is None


def test_deterministic_tie_break():
    stats = {"a": (0.5, 10.0), "b": (0.5, 10.0)}
    t = BackendOrderTuner(objective_id="o", backends=["b", "a"],
                          stats=stats, seed=1)
    assert t._optimal_order() == ["a", "b"]
    t2 = BackendOrderTuner(objective_id="o", backends=["a", "b"],
                           stats=stats, seed=1)
    assert t2._optimal_order() == ["a", "b"]


def test_bad_specs_rejected():
    with pytest.raises(TunerError):
        BackendOrderTuner(objective_id="o", backends=["a"], stats={"a": (1.0, 1.0)})
    with pytest.raises(TunerError):
        BackendOrderTuner(objective_id="o", backends=["a", "b"],
                          stats={"a": (1.0, 1.0)})  # b missing
    with pytest.raises(TunerError):
        BackendOrderTuner(objective_id="o", backends=["a", "b"],
                          stats={"a": (0.0, 1.0), "b": (1.0, 1.0)})
    with pytest.raises(TunerError):
        BackendOrderTuner(objective_id="", backends=["a", "b"],
                          stats={"a": (1.0, 1.0), "b": (1.0, 1.0)})


def test_missing_rank_param_surfaces():
    s = ConfigStore()  # no rank params registered
    with pytest.raises(Exception):  # ParameterError from store.describe
        _tuner().tune(_ctx(s))


def test_end_to_end_offline():
    store = _store(list(STATS))
    c = OptimizationController(store=store)
    c.register_objective("cost", lambda values: 0.0)
    c.register_tuner(_tuner())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=4)
    assert run.results[0].proposal_id != ""
    assert store.get("backend.rank.cheap-flaky") == 0  # offline: untouched
