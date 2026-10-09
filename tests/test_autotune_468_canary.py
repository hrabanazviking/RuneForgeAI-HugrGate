"""Slice 468 — canary optimization. Unit tests."""

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
from hugrgate.autotune.modes import CanaryDriver
from hugrgate.errors import AutotuneError


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _ctx(store, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=Mode.CANARY, run_id="run-c")


def _store():
    s = ConfigStore()
    s.register(TunableParameter(name="t", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    return s


def _proposal():
    return Proposal(proposal_id="p-c", tuner="t", changes={"t": 0.8},
                    objective_id="o", baseline=0.5, estimate=0.7, seed=3)


def test_canary_applies_and_leases():
    clock = _Clock()
    d = CanaryDriver(fraction=0.1, lease_seconds=60.0, clock=clock)
    store = _store()
    res = d.handle(_proposal(), _ctx(store))
    assert res.disposition == Disposition.CANARIED
    assert store.get("t") == 0.8  # applied (canaried)
    assert res.detail["fraction"] == 0.1
    lease = d.leases[0]
    assert lease.previous == {"t": 0.5}
    assert lease.status == "active"


def test_second_canary_rejected_while_active():
    d = CanaryDriver(clock=_Clock())
    ctx = _ctx(_store())
    d.handle(_proposal(), ctx)
    res = d.handle(_proposal(), ctx)
    assert res.disposition == Disposition.REJECTED


def test_poll_hold_when_healthy():
    d = CanaryDriver(clock=_Clock(),
                     guardrails=[lambda: (True, "ok")])
    store = _store()
    d.handle(_proposal(), _ctx(store))
    actions = d.poll(_ctx(store))
    assert actions[0]["action"] == "hold"
    assert store.get("t") == 0.8


def test_poll_rolls_back_on_guardrail_breach():
    d = CanaryDriver(clock=_Clock(),
                     guardrails=[lambda: (False, "error rate up")])
    store = _store()
    d.handle(_proposal(), _ctx(store))
    actions = d.poll(_ctx(store))
    assert actions[0]["action"] == "guardrail_rollback"
    assert store.get("t") == 0.5  # restored
    assert d.leases[0].status == "rolled_back"


def test_poll_rolls_back_on_guardrail_crash():
    def _boom():
        raise RuntimeError("no metrics")

    d = CanaryDriver(clock=_Clock(), guardrails=[_boom])
    store = _store()
    d.handle(_proposal(), _ctx(store))
    actions = d.poll(_ctx(store))
    assert actions[0]["action"] == "guardrail_rollback"  # fail closed
    assert store.get("t") == 0.5


def test_poll_expires_lease():
    clock = _Clock()
    d = CanaryDriver(lease_seconds=60.0, clock=clock)
    store = _store()
    d.handle(_proposal(), _ctx(store))
    clock.now += 61.0
    actions = d.poll(_ctx(store))
    assert actions[0]["action"] == "expired_rollback"
    assert store.get("t") == 0.5
    assert d.leases[0].status == "expired"


def test_promote_keeps_config():
    clock = _Clock()
    d = CanaryDriver(clock=clock)
    store = _store()
    res = d.handle(_proposal(), _ctx(store))
    d.promote(res.detail["lease_id"])
    assert d.leases[0].status == "promoted"
    clock.now += 10000.0
    assert d.poll(_ctx(store)) == []  # no active lease: nothing to do
    assert store.get("t") == 0.8  # stays applied


def test_promote_unknown_or_inactive():
    d = CanaryDriver(clock=_Clock())
    with pytest.raises(AutotuneError):
        d.promote("nope")
    store = _store()
    res = d.handle(_proposal(), _ctx(store))
    d.promote(res.detail["lease_id"])
    with pytest.raises(AutotuneError):
        d.promote(res.detail["lease_id"])  # already promoted


def test_bad_fraction_rejected():
    with pytest.raises(AutotuneError):
        CanaryDriver(fraction=1.5)
    with pytest.raises(AutotuneError):
        CanaryDriver(lease_seconds=0)


def test_controller_canary_cycle():
    clock = _Clock()
    store = _store()
    c = OptimizationController(store=store)
    driver = CanaryDriver(clock=clock)
    c.register_driver(driver)
    c.register_objective("o", lambda values: 0.0)

    class _T:
        name = "t"

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return _proposal()

    c.register_tuner(_T())
    run = c.run_cycle(mode=Mode.CANARY, seed=2)
    assert run.results[0].disposition == Disposition.CANARIED
    assert store.get("t") == 0.8
    # heartbeat with no guardrails: hold
    assert driver.poll(_ctx(store))[0]["action"] == "hold"
