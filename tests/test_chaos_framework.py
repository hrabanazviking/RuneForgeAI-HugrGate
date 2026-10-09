"""Slice 251 — chaos experiment framework tests."""

from __future__ import annotations

import json

import pytest

from hugrgate.chaos import (
    BlastRadius,
    ChaosExperiment,
    ExperimentRunner,
    Fault,
    ProbeOutcome,
    SteadyStateProbe,
)
from hugrgate.edge.chaos import ChaosError, ChaosRunner, FaultScenario
from hugrgate.errors import ChaosError as TaxonomyChaosError


def _ok_probe(name="healthy"):
    return SteadyStateProbe(name, lambda: ProbeOutcome(True, "fine"))


def _fault(name="f", inject=None, verify=None, rollback=None):
    return Fault(
        name=name,
        description=f"fault {name}",
        inject=inject or (lambda ctx: ctx.setdefault("injected", []).append(name)),
        verify=verify or (lambda ctx: None),
        rollback=rollback,
    )


def _experiment(**kw):
    base = dict(
        name="exp",
        hypothesis="the system survives",
        faults=(_fault(),),
        probes=(_ok_probe(),),
        blast_radius=BlastRadius(allowed_targets=frozenset({"lab"})),
        seed=7,
    )
    base.update(kw)
    return ChaosExperiment(**base)


# --- experiment definition validation -------------------------------------------

def test_experiment_rejects_empty_definition():
    with pytest.raises(TaxonomyChaosError, match="non-empty"):
        _experiment(name="  ")
    with pytest.raises(TaxonomyChaosError, match="hypothesis"):
        _experiment(hypothesis="")
    with pytest.raises(TaxonomyChaosError, match="at least one fault"):
        _experiment(faults=())
    with pytest.raises(TaxonomyChaosError, match="duplicate fault names"):
        _experiment(faults=(_fault("a"), _fault("a")))
    with pytest.raises(TaxonomyChaosError, match="non-empty"):
        Fault(name=" ", description="d", inject=lambda c: None,
              verify=lambda c: None)
    with pytest.raises(TaxonomyChaosError, match="non-empty"):
        Fault(name="n", description=" ", inject=lambda c: None,
              verify=lambda c: None)
    with pytest.raises(TaxonomyChaosError, match="non-empty"):
        SteadyStateProbe(" ", lambda: ProbeOutcome(True))


def test_blast_radius_blocks_disallowed_targets():
    runner = ExperimentRunner()
    with pytest.raises(TaxonomyChaosError, match="outside the experiment"):
        runner.run(_experiment(), "production")
    # but the allow-listed target runs
    report = runner.run(_experiment(), "lab")
    assert report.all_passed is True


def test_probe_exceptions_become_not_ok():
    def boom():
        raise RuntimeError("sensor dead")
    probe = SteadyStateProbe("s", boom)
    outcome = probe.run()
    assert outcome.ok is False
    assert "RuntimeError" in outcome.detail


def test_probe_returning_wrong_type_is_a_definition_error():
    probe = SteadyStateProbe("s", lambda: True)  # type: ignore[return-value]
    with pytest.raises(TaxonomyChaosError, match="must return ProbeOutcome"):
        probe.run()


# --- runner semantics -------------------------------------------------------------

def test_happy_path_records_everything():
    calls: list[str] = []
    fault = _fault(
        inject=lambda ctx: calls.append("inject"),
        verify=lambda ctx: calls.append("verify"),
        rollback=lambda ctx: calls.append("rollback"),
    )
    report = ExperimentRunner().run(_experiment(faults=(fault,)), "lab")
    assert calls == ["inject", "verify", "rollback"]
    assert report.all_passed is True
    assert report.steady_state_held is True
    assert report.faults[0].passed is True
    assert report.faults[0].to_dict()["passed"] is True
    json.dumps(report.to_dict())


def test_inject_failure_is_recorded_not_aborting():
    order: list[str] = []
    def bad_inject(ctx):
        order.append("bad")
        raise RuntimeError("injector broke")
    faults = (
        _fault("bad", inject=bad_inject),
        _fault("good", inject=lambda ctx: order.append("good")),
    )
    report = ExperimentRunner().run(_experiment(faults=faults), "lab")
    assert order == ["bad", "good"]  # run continued past the failure
    bad, good = report.faults
    assert bad.passed is False and bad.injected is False
    assert "inject failed" in bad.detail
    assert good.passed is True
    assert report.all_passed is False


def test_verify_failure_is_recorded():
    def bad_verify(ctx):
        raise AssertionError("degradation did not hold")
    report = ExperimentRunner().run(
        _experiment(faults=(_fault(verify=bad_verify),)), "lab")
    (result,) = report.faults
    assert result.injected is True
    assert result.verified is False
    assert result.rolled_back is True  # rollback still attempted
    assert result.passed is False
    assert "verify failed" in result.detail
    assert report.all_passed is False


def test_rollback_failure_is_recorded():
    def bad_rollback(ctx):
        raise OSError("cannot restore")
    report = ExperimentRunner().run(
        _experiment(faults=(_fault(rollback=bad_rollback),)), "lab")
    (result,) = report.faults
    assert result.rolled_back is False
    assert result.passed is False
    assert "rollback failed" in result.detail


def test_steady_state_delta_fails_the_experiment():
    states = {"post": True}
    probe = SteadyStateProbe(
        "health",
        lambda: ProbeOutcome(states["post"], "ok" if states["post"] else "down"))
    # before: healthy; the fault itself damages the world and never heals
    def damaging_inject(ctx):
        states["post"] = False
    report = ExperimentRunner().run(
        _experiment(faults=(_fault(inject=damaging_inject),),
                    probes=(probe,)),
        "lab")
    assert report.faults[0].passed is True  # the fault "worked"
    assert report.steady_state_held is False  # ...but it leaked damage
    assert report.all_passed is False


def test_unhealthy_before_state_fails_the_experiment():
    probe = SteadyStateProbe("health", lambda: ProbeOutcome(False, "already down"))
    report = ExperimentRunner().run(_experiment(probes=(probe,)), "lab")
    assert report.steady_state_held is False
    assert report.all_passed is False


def test_seed_makes_fault_sequences_reproducible():
    draws: list[list[float]] = []
    def sampling_inject(ctx):
        draws.append([ctx["rng"].random() for _ in range(3)])
    exp = _experiment(faults=(_fault(inject=sampling_inject),), seed=1234)
    ExperimentRunner().run(exp, "lab")
    ExperimentRunner().run(exp, "lab")
    assert draws[0] == draws[1]
    assert len(draws[0]) == 3


def test_dry_run_skips_injection_but_verifies_and_rolls_back():
    calls: list[str] = []
    fault = _fault(
        inject=lambda ctx: calls.append("inject"),
        verify=lambda ctx: calls.append("verify"),
        rollback=lambda ctx: calls.append("rollback"),
    )
    exp = _experiment(
        faults=(fault,),
        blast_radius=BlastRadius(allowed_targets=frozenset({"lab"}),
                                 dry_run=True),
    )
    report = ExperimentRunner().run(exp, "lab")
    assert calls == ["verify", "rollback"]
    assert report.dry_run is True
    assert report.faults[0].passed is True
    assert "dry-run" in report.faults[0].detail


def test_last_report_and_report_contents():
    runner = ExperimentRunner()
    assert runner.last_report("exp") is None
    report = runner.run(_experiment(), "lab")
    assert runner.last_report("exp") is report
    d = report.to_dict()
    assert d["experiment"] == "exp"
    assert d["hypothesis"] == "the system survives"
    assert d["target"] == "lab"
    assert d["seed"] == 7
    assert d["steady_before"] == {"healthy": {"ok": True, "detail": "fine"}}
    assert d["duration_s"] >= 0.0


# --- slice 251 hardening of hugrgate.edge.chaos -----------------------------------

def test_edge_scenario_pre_check_failure_fails_fast():
    runner = ChaosRunner()
    def pre():
        raise RuntimeError("world already unhealthy")
    ran: list[str] = []
    runner.register(FaultScenario(
        "s", "d", lambda: ran.append("run"), pre_check=pre))
    (result,) = runner.run_all()
    assert result.passed is False
    assert "pre-check failed" in result.detail
    assert ran == []  # fault never injected into an unhealthy world


def test_edge_scenario_post_check_catches_leaked_damage():
    runner = ChaosRunner()
    def post():
        raise AssertionError("damage leaked")
    runner.register(FaultScenario(
        "s", "d", lambda: None, post_check=post))
    (result,) = runner.run_all()
    assert result.passed is False
    assert "post-check failed" in result.detail
    assert "leaked" in result.detail


def test_edge_scenario_healthy_checks_pass_through():
    runner = ChaosRunner()
    order: list[str] = []
    runner.register(FaultScenario(
        "s", "d",
        lambda: order.append("run"),
        pre_check=lambda: order.append("pre"),
        post_check=lambda: order.append("post")))
    (result,) = runner.run_all()
    assert result.passed is True
    assert order == ["pre", "run", "post"]


def test_edge_run_one_and_unknown_name():
    runner = ChaosRunner()
    runner.register(FaultScenario("s", "d", lambda: None))
    result = runner.run_one("s")
    assert result.passed is True
    with pytest.raises(ChaosError, match="unknown chaos scenario"):
        runner.run_one("nope")
