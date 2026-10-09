"""Slice 453 — constraint specification. Unit tests."""

from __future__ import annotations

import pytest

from hugrgate.autotune.constraints import (
    ConstraintSet,
    ConstraintSpec,
    change_within,
    implies,
    mutual_exclusion,
    requires,
    sum_leq,
    within_bounds,
)
from hugrgate.errors import ConstraintViolation


def test_within_bounds():
    c = within_bounds("t", 0.1, 0.9)
    assert c.check({"t": 0.5}) is None
    assert c.check({"t": 0.95}) is not None
    assert c.check({}) is not None  # missing param fails closed


def test_requires_predicate():
    c = requires("n", lambda x: x % 2 == 0, "n must be even")
    assert c.check({"n": 4}) is None
    assert c.check({"n": 3}) is not None


def test_implies():
    c = implies("backend", "canary", "shadow", [False])
    assert c.check({"backend": "canary", "shadow": False}) is None
    v = c.check({"backend": "canary", "shadow": True})
    assert v is not None and "shadow" in v.message
    assert c.check({"backend": "stable", "shadow": True}) is None


def test_mutual_exclusion():
    c = mutual_exclusion(["a", "b", "c"])
    assert c.check({"a": True, "b": False, "c": 0}) is None
    assert c.check({"a": True, "b": True}) is not None
    assert c.check({}) is None  # none active is fine


def test_sum_leq():
    c = sum_leq(["x", "y"], 1.0)
    assert c.check({"x": 0.4, "y": 0.5}) is None
    assert c.check({"x": 0.6, "y": 0.5}) is not None
    assert c.check({"x": 0.4}) is None  # missing params count as 0


def test_change_within():
    c = change_within("t", {"t": 0.5}, 0.1)
    assert c.check({"t": 0.55}) is None
    assert c.check({"t": 0.7}) is not None
    assert c.check({}) is None  # untouched param passes


def test_predicate_exception_becomes_violation():
    def _boom(values):
        raise RuntimeError("bad")

    c = ConstraintSpec(constraint_id="x", predicate=_boom, message="m")
    with pytest.raises(ConstraintViolation):
        c.check({})


def test_set_validate_raises_first():
    s = ConstraintSet([within_bounds("t", 0.0, 0.5, "c1"),
                       within_bounds("t", 0.0, 0.25, "c2")])
    with pytest.raises(ConstraintViolation) as ei:
        s.validate({"t": 0.4})
    assert ei.value.details["constraint"] == "c2"
    assert len(s) == 2
    assert s.ids == ["c1", "c2"]


def test_set_validate_all_collects():
    s = ConstraintSet([within_bounds("t", 0.0, 0.1, "c1"),
                       within_bounds("u", 0.0, 0.1, "c2")])
    vs = s.validate_all({"t": 0.5, "u": 0.5})
    assert [v.constraint_id for v in vs] == ["c1", "c2"]
    assert s.validate_all({"t": 0.05, "u": 0.05}) == []


def test_set_rejects_duplicate_ids():
    s = ConstraintSet([within_bounds("t", 0.0, 1.0, "c1")])
    with pytest.raises(ConstraintViolation):
        s.add(within_bounds("u", 0.0, 1.0, "c1"))


def test_as_callable_integrates_with_controller():
    from hugrgate.autotune.controller import (
        ConfigStore,
        Mode,
        OptimizationController,
        Proposal,
        TunableParameter,
        TuningContext,
    )

    store = ConfigStore()
    store.register(TunableParameter(name="t", dtype="float", default=0.5,
                                    lo=0.0, hi=1.0))
    c = OptimizationController(store=store)
    c.register_objective("o", lambda values: 0.0)
    for fn in ConstraintSet([within_bounds("t", 0.0, 0.6)]).as_callables():
        c.register_constraint(fn)

    class _T:
        name = "t"

        def tune(self, ctx: TuningContext) -> Proposal | None:
            return Proposal(proposal_id="p", tuner="t", changes={"t": 0.9},
                            objective_id="o", baseline=0.0, estimate=1.0,
                            seed=0)

    c.register_tuner(_T())
    run = c.run_cycle(mode=Mode.OFFLINE)
    assert run.results[0].disposition.value == "rejected"


def test_violation_to_dict():
    v = within_bounds("t", 0.0, 1.0).check({"t": 5.0})
    assert v is not None
    assert v.to_dict()["severity"] == "hard"
