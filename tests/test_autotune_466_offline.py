"""Slice 466 — offline optimization mode. Unit tests."""

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
from hugrgate.autotune.modes import OfflineDriver
from hugrgate.errors import AutotuneError


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.OFFLINE, run_id="run-1")


def _store():
    s = ConfigStore()
    s.register(TunableParameter(name="t", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    return s


def _proposal():
    return Proposal(proposal_id="p-1", tuner="t", changes={"t": 0.8},
                    objective_id="o", baseline=0.5, estimate=0.7, seed=3)


def test_handle_records_without_applying():
    d = OfflineDriver()
    store = _store()
    res = d.handle(_proposal(), _ctx(store))
    assert res.disposition == Disposition.RECORDED
    assert store.get("t") == 0.5  # untouched
    assert len(d.journal) == 1
    assert d.journal[0]["proposal"]["changes"] == {"t": 0.8}
    assert d.journal[0]["run_id"] == "run-1"


def test_replay_scores_and_records():
    d = OfflineDriver()
    d.handle(_proposal(), _ctx(_store()))
    score = d.replay("p-1", lambda changes: changes["t"] * 2)
    assert score == pytest.approx(1.6)
    assert d.journal[0]["replay"] == {"score": 1.6}


def test_replay_unknown_proposal():
    d = OfflineDriver()
    with pytest.raises(AutotuneError):
        d.replay("missing", lambda c: 0.0)


def test_replay_evaluator_crash_isolated():
    d = OfflineDriver()
    d.handle(_proposal(), _ctx(_store()))

    def _boom(changes):
        raise RuntimeError("bad data")

    with pytest.raises(AutotuneError):
        d.replay("p-1", _boom)
    assert d.journal[0]["replay"] is None  # failed replay not recorded


def test_export_is_deep_copy():
    d = OfflineDriver()
    d.handle(_proposal(), _ctx(_store()))
    out = d.export()
    out[0]["proposal"]["changes"]["t"] = 999
    assert d.journal[0]["proposal"]["changes"] == {"t": 0.8}
    d.clear()
    assert d.journal == []


def test_controller_uses_registered_offline_driver():
    store = _store()
    c = OptimizationController(store=store)
    driver = OfflineDriver()
    c.register_driver(driver)
    c.register_objective("o", lambda values: 0.0)

    class _T:
        name = "t"

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return _proposal()

    c.register_tuner(_T())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=1)
    assert run.results[0].disposition == Disposition.RECORDED
    assert len(driver.journal) == 1
    # replay through the driver after the cycle
    assert driver.replay("p-1", lambda ch: 1.0) == 1.0
