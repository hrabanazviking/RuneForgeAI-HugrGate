"""Slice 451 — optimization controller. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.controller import (
    ConfigStore,
    Disposition,
    DriverResult,
    Mode,
    ModeDriver,
    OptimizationController,
    Proposal,
    TunableParameter,
    TuningContext,
)
from hugrgate.errors import (
    AutotuneError,
    ConstraintViolation,
    ParameterError,
)


def _store() -> ConfigStore:
    s = ConfigStore()
    s.register(TunableParameter(name="threshold", dtype="float",
                                default=0.5, lo=0.0, hi=1.0,
                                owner="slice-454"))
    s.register(TunableParameter(name="batch_size", dtype="int",
                                default=8, lo=1, hi=64, owner="slice-458"))
    s.register(TunableParameter(name="eviction", dtype="str",
                                default="lru", choices=("lru", "lfu"),
                                owner="slice-457"))
    s.register(TunableParameter(name="abstain_enabled", dtype="bool",
                                default=True, owner="slice-455"))
    return s


class _ImprovingTuner:
    name = "improver"

    def __init__(self, changes: dict) -> None:
        self._changes = changes

    def tune(self, ctx: TuningContext) -> Proposal | None:
        return Proposal(proposal_id="p1", tuner=self.name,
                        changes=dict(self._changes),
                        objective_id="obj", baseline=0.5, estimate=0.7,
                        seed=ctx.seed)


class _NullTuner:
    name = "nuller"

    def tune(self, ctx: TuningContext) -> Proposal | None:
        return None


class _CrashingTuner:
    name = "crasher"

    def tune(self, ctx: TuningContext) -> Proposal | None:
        raise RuntimeError("boom")


def _controller(**kw) -> OptimizationController:
    c = OptimizationController(store=_store())
    c.register_objective("obj", lambda values: 0.5)
    return c


# -- parameter definition ----------------------------------------------

def test_bad_dtype_rejected():
    with pytest.raises(ParameterError):
        TunableParameter(name="x", dtype="complex", default=1)


def test_numeric_requires_bounds():
    with pytest.raises(ParameterError):
        TunableParameter(name="x", dtype="float", default=0.5)


def test_inverted_bounds_rejected():
    with pytest.raises(ParameterError):
        TunableParameter(name="x", dtype="float", default=0.5,
                         lo=1.0, hi=0.0)


def test_str_requires_choices_and_member_default():
    with pytest.raises(ParameterError):
        TunableParameter(name="x", dtype="str", default="a")
    with pytest.raises(ParameterError):
        TunableParameter(name="x", dtype="str", default="z",
                         choices=("a", "b"))


def test_default_out_of_bounds_rejected():
    with pytest.raises(ParameterError):
        TunableParameter(name="x", dtype="float", default=9.0,
                         lo=0.0, hi=1.0)


def test_bool_rejects_int():
    p = TunableParameter(name="b", dtype="bool", default=True)
    with pytest.raises(ParameterError):
        p.coerce(1)


def test_duplicate_registration_rejected():
    s = _store()
    with pytest.raises(ParameterError):
        s.register(TunableParameter(name="threshold", dtype="float",
                                    default=0.1, lo=0.0, hi=1.0))


def test_unknown_parameter_errors():
    s = _store()
    with pytest.raises(ParameterError):
        s.get("nope")
    with pytest.raises(ParameterError):
        s.apply({"nope": 1})


# -- store semantics ----------------------------------------------------

def test_apply_all_or_nothing():
    s = _store()
    before = s.snapshot()
    with pytest.raises(ParameterError):
        s.apply({"threshold": 0.9, "batch_size": 999})
    assert s.snapshot() == before


def test_apply_coerces_and_returns():
    s = _store()
    out = s.apply({"threshold": 1, "eviction": "lfu"})
    assert out == {"threshold": 1.0, "eviction": "lfu"}
    assert s.get("threshold") == 1.0


def test_snapshot_restore_roundtrip():
    s = _store()
    snap = s.snapshot()
    s.apply({"threshold": 0.9})
    s.restore(snap)
    assert s.get("threshold") == 0.5


def test_restore_rejects_bad_snapshot():
    s = _store()
    with pytest.raises(ParameterError):
        s.restore({"threshold": 42.0})
    with pytest.raises(ParameterError):
        s.restore({"ghost": 1})


# -- controller cycle ----------------------------------------------------

def test_cycle_records_proposal_offline():
    c = _controller()
    c.register_tuner(_ImprovingTuner({"threshold": 0.8}))
    run = c.run_cycle(mode=Mode.OFFLINE, seed=7)
    assert len(run.results) == 1
    assert run.results[0].disposition == Disposition.RECORDED
    # offline must not touch live config
    assert c.store.get("threshold") == 0.5


def test_null_tuner_skipped():
    c = _controller()
    c.register_tuner(_NullTuner())
    run = c.run_cycle()
    assert run.results[0].disposition == Disposition.SKIPPED


def test_crashing_tuner_isolated():
    c = _controller()
    c.register_tuner(_CrashingTuner())
    c.register_tuner(_ImprovingTuner({"threshold": 0.8}))
    run = c.run_cycle()
    kinds = [r.disposition for r in run.results]
    assert Disposition.SKIPPED in kinds
    assert Disposition.RECORDED in kinds
    assert any("crasher" in n for n in run.notes)


def test_constraint_violation_rejects_proposal():
    c = _controller()
    c.register_tuner(_ImprovingTuner({"threshold": 0.99}))

    def _cap(values):
        if values["threshold"] > 0.9:
            raise ConstraintViolation("threshold too high")

    c.register_constraint(_cap)
    run = c.run_cycle()
    assert run.results[0].disposition == Disposition.REJECTED


def test_out_of_bounds_change_never_reaches_driver():
    seen: list[Proposal] = []

    class _Spy(ModeDriver):
        mode = Mode.OFFLINE

        def handle(self, proposal: Proposal,
                   ctx: TuningContext) -> DriverResult:
            seen.append(proposal)
            return DriverResult(proposal_id=proposal.proposal_id,
                                disposition=Disposition.RECORDED)

    c = _controller()
    c.register_driver(_Spy())
    # 1.5 is outside the registered [0, 1] bound; store.apply inside
    # candidate construction raises ParameterError before the driver.
    c.register_tuner(_ImprovingTuner({"threshold": 1.5}))
    with pytest.raises(ParameterError):
        c.run_cycle()
    assert seen == []


def test_duplicate_tuner_rejected():
    c = _controller()
    c.register_tuner(_ImprovingTuner({}))
    with pytest.raises(AutotuneError):
        c.register_tuner(_ImprovingTuner({}))


def test_unnamed_tuner_rejected():
    c = _controller()

    class _NoName:
        def tune(self, ctx):
            return None

    with pytest.raises(AutotuneError):
        c.register_tuner(_NoName())  # type: ignore[arg-type]


def test_unknown_objective_scores_error():
    c = _controller()

    class _Probe:
        name = "probe"

        def tune(self, ctx: TuningContext):
            with pytest.raises(AutotuneError):
                ctx.score("missing", {})
            return None

    c.register_tuner(_Probe())
    c.run_cycle()


def test_history_journaled():
    c = _controller()
    c.register_tuner(_NullTuner())
    run = c.run_cycle(seed=3)
    assert c.history[-1].run_id == run.run_id
    d = run.to_dict()
    assert d["mode"] == "offline" and d["seed"] == 3
    assert d["results"][0]["disposition"] == "skipped"


def test_proposal_delta_and_dict():
    p = Proposal(proposal_id="p", tuner="t", changes={"a": 1},
                 objective_id="o", baseline=0.4, estimate=0.6, seed=1)
    assert p.delta == pytest.approx(0.2)
    assert p.to_dict()["delta"] == pytest.approx(0.2)
