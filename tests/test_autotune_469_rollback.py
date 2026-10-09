"""Slice 469 — rollback triggers. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Mode,
    Proposal,
    TunableParameter,
    TuningContext,
)
from hugrgate.autotune.modes import CanaryDriver
from hugrgate.autotune.rollback import (
    RollbackController,
    RollbackTrigger,
)
from hugrgate.errors import RollbackError


def _metric(values):
    it = iter(values)

    def _m():
        return next(it, values[-1])

    return _m


def test_trigger_fires_after_sustained_breaches():
    restored = []
    rc = RollbackController(restore=lambda: restored.append(1))
    rc.add_trigger(RollbackTrigger(name="err", metric=_metric([0.1, 0.9, 0.9,
                                                               0.9]),
                                   direction="gt", threshold=0.5,
                                   sustained=3))
    assert rc.check() == []  # 0.1 ok
    assert rc.check() == []  # 1 breach
    assert rc.check() == []  # 2 breaches
    fired = rc.check()  # 3 breaches -> fire
    assert len(fired) == 1 and fired[0].trigger == "err"
    assert restored == [1]
    # disarmed until reset
    assert rc.check() == []
    rc.reset("err")
    assert rc.check() == []  # re-armed: single breach, no fire yet


def test_breach_counter_resets_on_recovery():
    rc = RollbackController(restore=lambda: None)
    rc.add_trigger(RollbackTrigger(name="t", metric=_metric([0.9, 0.9, 0.1,
                                                            0.9, 0.9, 0.9]),
                                   direction="gt", threshold=0.5,
                                   sustained=3))
    rc.check()  # breach 1
    rc.check()  # breach 2
    rc.check()  # 0.1: recovery, counter resets
    assert rc.check() == []  # breach 1 again
    assert rc.check() == []  # breach 2
    assert len(rc.check()) == 1  # breach 3 -> fire


def test_lt_direction():
    rc = RollbackController(restore=lambda: None)
    rc.add_trigger(RollbackTrigger(name="q", metric=_metric([0.9, 0.1]),
                                   direction="lt", threshold=0.5,
                                   sustained=1))
    assert rc.check() == []
    assert len(rc.check()) == 1


def test_duplicate_and_unknown_trigger():
    rc = RollbackController()
    t = RollbackTrigger(name="t", metric=lambda: 0.0, direction="gt",
                        threshold=1.0)
    rc.add_trigger(t)
    with pytest.raises(RollbackError):
        rc.add_trigger(t)
    with pytest.raises(RollbackError):
        rc.reset("missing")


def test_bad_trigger_specs():
    with pytest.raises(RollbackError):
        RollbackTrigger(name="", metric=lambda: 0.0, direction="gt",
                        threshold=1.0)
    with pytest.raises(RollbackError):
        RollbackTrigger(name="t", metric=lambda: 0.0, direction="xx",
                        threshold=1.0)
    with pytest.raises(RollbackError):
        RollbackTrigger(name="t", metric=lambda: 0.0, direction="gt",
                        threshold=1.0, sustained=0)


def test_metric_crash_is_breach_and_surfaces():
    def _boom():
        raise RuntimeError("no metrics")

    rc = RollbackController(restore=lambda: None)
    rc.add_trigger(RollbackTrigger(name="t", metric=_boom, direction="gt",
                                   threshold=1.0, sustained=1))
    with pytest.raises(RollbackError):
        rc.check()  # fail closed: unreadable metric surfaces


def test_restore_failure_raises_rollback_error():
    def _bad_restore():
        raise OSError("disk gone")

    rc = RollbackController(restore=_bad_restore)
    rc.add_trigger(RollbackTrigger(name="t", metric=lambda: 9.0,
                                   direction="gt", threshold=1.0,
                                   sustained=1))
    with pytest.raises(RollbackError) as ei:
        rc.check()
    assert "restore failed" in str(ei.value)


def test_no_restore_registered():
    rc = RollbackController()  # no restore fn
    rc.add_trigger(RollbackTrigger(name="t", metric=lambda: 9.0,
                                   direction="gt", threshold=1.0,
                                   sustained=1))
    with pytest.raises(RollbackError):
        rc.check()


def test_canary_guardrail_integration():
    """Triggers wired into a canary driver roll back exactly once."""
    store = ConfigStore()
    store.register(TunableParameter(name="t", dtype="float", default=0.5,
                                    lo=0.0, hi=1.0))
    rc = RollbackController()  # no restore: the driver owns rollback
    rc.add_trigger(RollbackTrigger(name="err", metric=_metric([0.9, 0.9]),
                                   direction="gt", threshold=0.5,
                                   sustained=2,
                                   description="error rate"))
    driver = CanaryDriver(guardrails=rc.as_canary_guardrails())
    ctx = TuningContext(store=store, objectives={}, constraints=[],
                        seed=1, mode=Mode.CANARY, run_id="r")
    prop = Proposal(proposal_id="p", tuner="t", changes={"t": 0.8},
                    objective_id="o", baseline=0.0, estimate=1.0, seed=1)
    driver.handle(prop, ctx)
    assert store.get("t") == 0.8
    assert driver.poll(ctx)[0]["action"] == "hold"  # 1 breach
    actions = driver.poll(ctx)  # 2 breaches -> guardrail breach
    assert actions[0]["action"] == "guardrail_rollback"
    assert "error rate" in actions[0]["reason"]
    assert store.get("t") == 0.5  # exactly one restore, by the driver
    assert len(rc.events) == 1


def test_event_to_dict():
    rc = RollbackController(restore=lambda: None)
    rc.add_trigger(RollbackTrigger(name="t", metric=lambda: 9.0,
                                   direction="gt", threshold=1.0,
                                   sustained=1))
    fired = rc.check()
    d = fired[0].to_dict()
    assert d["trigger"] == "t" and d["breaches"] == 1
