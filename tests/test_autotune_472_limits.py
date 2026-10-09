"""Slice 472 — optimizer safety limits. Unit tests."""

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
from hugrgate.autotune.limits import SafetyEnforcer, SafetyLimits
from hugrgate.autotune.modes import OfflineDriver
from hugrgate.errors import UnsafeProposalError


def _ctx(store, mode=Mode.OFFLINE, seed=5):
    return TuningContext(store=store, objectives={}, constraints=[],
                         seed=seed, mode=mode, run_id="r")


def _store():
    s = ConfigStore()
    s.register(TunableParameter(name="t", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    s.register(TunableParameter(name="u", dtype="float", default=0.5,
                                lo=0.0, hi=1.0))
    s.register(TunableParameter(name="frozen_p", dtype="float",
                                default=0.1, lo=0.0, hi=1.0))
    return s


def _proposal(changes=None, pid="p-1"):
    return Proposal(proposal_id=pid, tuner="t", changes=changes or {"t": 0.6},
                    objective_id="o", baseline=0.0, estimate=1.0, seed=1)


def test_kill_switch_rejects_everything():
    enf = SafetyEnforcer(SafetyLimits(kill_switch=True))
    with pytest.raises(UnsafeProposalError):
        enf.check_proposal(_proposal(), _ctx(_store()))


def test_frozen_params_rejected():
    enf = SafetyEnforcer(SafetyLimits(frozen_params=("frozen_p",)))
    with pytest.raises(UnsafeProposalError) as ei:
        enf.check_proposal(_proposal({"frozen_p": 0.9}), _ctx(_store()))
    assert ei.value.details["params"] == ["frozen_p"]
    # untouched frozen param is fine
    enf.check_proposal(_proposal({"t": 0.6}), _ctx(_store()))


def test_blast_radius():
    enf = SafetyEnforcer(SafetyLimits(max_params_per_proposal=1))
    with pytest.raises(UnsafeProposalError):
        enf.check_proposal(_proposal({"t": 0.6, "u": 0.6}), _ctx(_store()))
    enf.check_proposal(_proposal({"t": 0.6}), _ctx(_store()))


def test_step_size_limit():
    enf = SafetyEnforcer(SafetyLimits(max_step_fraction=0.25))
    # current t=0.5, width=1.0 -> max step 0.25
    enf.check_proposal(_proposal({"t": 0.7}), _ctx(_store()))
    with pytest.raises(UnsafeProposalError) as ei:
        enf.check_proposal(_proposal({"t": 0.9}), _ctx(_store()))
    assert ei.value.details["param"] == "t"


def test_mode_allowlist():
    enf = SafetyEnforcer(
        SafetyLimits(allowed_modes=(Mode.OFFLINE, Mode.SHADOW)))
    enf.check_proposal(_proposal(), _ctx(_store(), mode=Mode.SHADOW))
    with pytest.raises(UnsafeProposalError):
        enf.check_proposal(_proposal(), _ctx(_store(), mode=Mode.APPLIED))
    with pytest.raises(UnsafeProposalError):
        enf.check_proposal(_proposal(), _ctx(_store(), mode=Mode.CANARY))


def test_rate_limit():
    now = [1000.0]
    enf = SafetyEnforcer(SafetyLimits(max_cycles_per_hour=2),
                         clock=lambda: now[0])
    enf.check_rate()
    enf.check_rate()
    with pytest.raises(UnsafeProposalError):
        enf.check_rate()
    now[0] += 3601.0  # window slides
    enf.check_rate()  # ok again


def test_bad_limits_rejected():
    with pytest.raises(UnsafeProposalError):
        SafetyLimits(max_params_per_proposal=0)
    with pytest.raises(UnsafeProposalError):
        SafetyLimits(max_step_fraction=0.0)
    with pytest.raises(UnsafeProposalError):
        SafetyLimits(max_cycles_per_hour=0)


def test_guarded_driver_rejects_unsafe():
    enf = SafetyEnforcer(SafetyLimits(frozen_params=("t",)))
    guarded = enf.as_driver(OfflineDriver())
    store = _store()
    res = guarded.handle(_proposal({"t": 0.6}), _ctx(store))
    assert res.disposition == Disposition.REJECTED
    assert res.detail["reason"] == "safety_limits"
    assert store.get("t") == 0.5


def test_guarded_driver_passes_safe():
    enf = SafetyEnforcer()
    driver = OfflineDriver()
    guarded = enf.as_driver(driver)
    res = guarded.handle(_proposal({"t": 0.6}), _ctx(_store()))
    assert res.disposition == Disposition.RECORDED
    assert len(driver.journal) == 1


def test_guarded_controller_wiring():
    store = _store()
    c = OptimizationController(store=store)
    c.register_objective("o", lambda values: 0.0)
    enf = SafetyEnforcer(SafetyLimits(frozen_params=("t",)))
    enf.guarded_controller(c, modes=(Mode.OFFLINE,))

    class _T:
        name = "t"

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return _proposal({"t": 0.6})

    c.register_tuner(_T())
    run = c.run_cycle(mode=Mode.OFFLINE, seed=1)
    assert run.results[0].disposition == Disposition.REJECTED
    assert run.results[0].detail["reason"] == "safety_limits"
