"""Slice 467 — shadow optimization mode. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Disposition,
    Mode,
    OptimizationController,
    Proposal,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.modes import ShadowDriver
from hugrgate.errors import AutotuneError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.SHADOW, run_id="run-9")


def _store():
    s = ConfigStore()
    s.register(TunableParameter(name="t", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    return s


def _proposal(changes=None):
    return Proposal(proposal_id="p-s", tuner="t",
                    changes=changes or {"t": 0.8}, objective_id="o",
                    baseline=0.5, estimate=0.7, seed=3)


def _driver(**kw):
    # samples carry a target; scorers reward closeness of t to it.
    samples = [{"target": 0.8 + 0.01 * i} for i in range(20)]
    base = dict(samples=samples,
                live_scorer=lambda v, s: 1.0 - abs(v["t"] - s["target"]),
                shadow_scorer=lambda v, s: 1.0 - abs(v["t"] - s["target"]))
    base.update(kw)
    return ShadowDriver(**base)


def test_shadow_would_win():
    d = _driver()
    res = d.handle(_proposal({"t": 0.8}), _ctx(_store()))  # live t=0.5
    assert res.disposition == Disposition.SHADOWED
    assert res.detail["verdict"] == "would_win"
    assert res.detail["delta"] > 0
    assert d.journal[0]["n_samples"] == 20


def test_shadow_would_lose():
    d = _driver()
    res = d.handle(_proposal({"t": 0.0}), _ctx(_store()))
    assert res.detail["verdict"] == "would_lose"


def test_shadow_tie():
    d = _driver(min_delta=0.5)
    res = d.handle(_proposal({"t": 0.51}), _ctx(_store()))
    assert res.detail["verdict"] == "tie"


def test_shadow_never_applies():
    store = _store()
    d = _driver()
    d.handle(_proposal({"t": 0.9}), _ctx(store))
    assert store.get("t") == 0.5


def test_scorer_crash_isolated():
    def _boom(values, sample):
        raise RuntimeError("bad scorer")

    d = _driver(shadow_scorer=_boom)
    with pytest.raises(AutotuneError):
        d.handle(_proposal(), _ctx(_store()))
    assert d.journal == []  # crashed comparisons are not journaled


def test_driver_requires_samples_and_scorers():
    with pytest.raises(AutotuneError):
        ShadowDriver(samples=[])
    with pytest.raises(AutotuneError):
        ShadowDriver(samples=[{"a": 1}])


def test_controller_shadow_cycle():
    store = _store()
    c = OptimizationController(store=store)
    driver = _driver()
    c.register_driver(driver)
    c.register_objective("o", lambda values: 0.0)

    class _T:
        name = "t"

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return _proposal({"t": 0.8})

    c.register_tuner(_T())
    run = c.run_cycle(mode=Mode.SHADOW, seed=2)
    assert run.results[0].disposition == Disposition.SHADOWED
    assert run.results[0].detail["verdict"] == "would_win"
    assert store.get("t") == 0.5  # shadow: compared, never applied
