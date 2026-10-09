"""Slice 073 — routing fuzz tests (incl. adversarial)."""

from __future__ import annotations

import pytest

from hugrgate import (
    Abstention,
    Backend,
    BackendRegistry,
    DecisionPolicy,
    DecisionResult,
    DecisionSpec,
)
from hugrgate.ladder import LadderRung
from hugrgate.routing import (
    LadderRouterV2,
    SerialPlanExecutor,
    run_fuzz,
)

# -- harness: fixed seeds, zero violations ------------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fuzz_fixed_seeds_no_violations(seed):
    report = run_fuzz(seed, iterations=60)
    assert report["iterations"] == 60
    assert report["decided"] + report["abstained"] == 60
    assert report["violations"] == [], \
        "\n".join(report["violations"][:5])


def test_fuzz_report_shape():
    report = run_fuzz(99, iterations=10)
    assert set(report) == {"seed", "iterations", "decided", "abstained",
                           "violations"}


# -- targeted adversarial backends ----------------------------------------------------

class HostileBackend(Backend):
    """Each flavor of hostile behavior, on demand."""

    def __init__(self, name, flavor):
        self.name = name
        self.flavor = flavor

    def capabilities(self):
        return {"spec_types": ["categorical"]}

    def supports(self, spec):
        return spec.type == "categorical"

    def evaluate(self, state, spec, context=None):
        if self.flavor == "raiser":
            raise RuntimeError("hostile crash attempt")
        if self.flavor == "liar":
            return DecisionResult(value="a", probability=1.5,
                                  distribution={"a": 1.5, "b": -0.5},
                                  backend=self.name)
        if self.flavor == "nan":
            return DecisionResult(value="a", probability=float("nan"),
                                  distribution={"a": 0.5, "b": 0.5},
                                  backend=self.name)
        if self.flavor == "none":
            return None
        raise AssertionError("unknown flavor")


def spec():
    return DecisionSpec(type="categorical", options=["a", "b"])


def router_for(backend):
    reg = BackendRegistry()
    reg.register(backend)
    return LadderRouterV2(reg, rungs=[LadderRung(backend.name, 0.9)],
                          executor=SerialPlanExecutor())


@pytest.mark.parametrize("flavor", ["raiser", "liar", "nan", "none"])
def test_hostile_backend_contained_not_crash(flavor):
    """Hostile backends become audited rung failures, never escape."""
    router = router_for(HostileBackend("evil", flavor))
    with pytest.raises(Abstention):  # ladder exhausted, not a crash
        router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    outcomes = [e.outcome for e in router.last_audit]
    assert outcomes == ["backend_error"]


def test_hostile_then_honest_climb_continues():
    evil = HostileBackend("evil", "raiser")

    class Good(Backend):
        name = "good"

        def capabilities(self):
            return {"spec_types": ["categorical"]}

        def supports(self, spec):
            return spec.type == "categorical"

        def evaluate(self, state, spec, context=None):
            n = len(spec.options)
            rest = 0.05 / (n - 1)
            return DecisionResult(
                value="a", probability=0.95,
                distribution={o: (0.95 if o == "a" else rest)
                              for o in spec.options},
                backend=self.name)

    reg = BackendRegistry()
    reg.register(evil)
    reg.register(Good())
    router = LadderRouterV2(
        reg, rungs=[LadderRung("evil", 0.9), LadderRung("good", 0.9)])
    won = router.decide({}, spec(), DecisionPolicy(minimum_probability=0.9))
    assert won.backend == "good"
    by_name = {e.backend_name: e.outcome for e in router.last_audit}
    assert by_name["evil"] == "backend_error"
    assert by_name["good"] == "accepted"


def test_lying_probability_never_accepted():
    # Even with gate 0.0, a p=1.5 result must fail validation, not win.
    router = router_for(HostileBackend("liar", "liar"))
    with pytest.raises(Abstention):
        router.decide({}, spec(), DecisionPolicy(minimum_probability=0.0))
