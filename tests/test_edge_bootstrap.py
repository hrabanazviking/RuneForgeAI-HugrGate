"""Slice 192 — offline-first bootstrap tests."""

from __future__ import annotations

import pytest

from hugrgate.edge.bootstrap import (
    BootstrapContext,
    BootstrapPlan,
    BootstrapStep,
    OfflineBootstrapError,
    default_edge_plan,
)
from hugrgate.edge.memory import MemoryManager
from hugrgate.edge.platform import PlatformProbe


def _ok_step(name: str, **kw) -> BootstrapStep:
    calls = kw.pop("calls", None)
    def action(ctx: BootstrapContext) -> None:
        ctx.set(name, True)
        if calls is not None:
            calls.append(name)
    return BootstrapStep(name=name, action=action, **kw)


# --- plan mechanics ---------------------------------------------------------------------

def test_run_executes_in_order_and_records():
    calls: list[str] = []
    plan = BootstrapPlan([_ok_step("a", calls=calls),
                          _ok_step("b", calls=calls)])
    ctx = BootstrapContext()
    outcomes = plan.run(ctx)
    assert calls == ["a", "b"]
    assert [o.status for o in outcomes] == ["ok", "ok"]
    assert all(o.duration_s >= 0 for o in outcomes)
    assert ctx.get("a") is True
    assert plan.succeeded()


def test_critical_failure_aborts_rest_skip():
    def boom(ctx: BootstrapContext) -> None:
        raise RuntimeError("nope")
    plan = BootstrapPlan([
        _ok_step("first"),
        BootstrapStep(name="bad", action=boom, critical=True),
        _ok_step("never"),
    ])
    outcomes = plan.run()
    assert [o.status for o in outcomes] == ["ok", "failed", "skipped"]
    assert "RuntimeError: nope" in outcomes[1].detail
    assert not plan.succeeded()


def test_non_critical_failure_continues():
    def boom(ctx: BootstrapContext) -> None:
        raise RuntimeError("nope")
    plan = BootstrapPlan([
        BootstrapStep(name="bad", action=boom, critical=False),
        _ok_step("after"),
    ])
    outcomes = plan.run()
    assert [o.status for o in outcomes] == ["failed", "ok"]
    assert not plan.succeeded()  # any failure -> not succeeded


def test_dry_run_skips_everything():
    calls: list[str] = []
    plan = BootstrapPlan([_ok_step("a", calls=calls)])
    outcomes = plan.run(dry_run=True)
    assert [o.status for o in outcomes] == ["skipped"]
    assert calls == []
    assert not plan.succeeded()


def test_duplicate_step_rejected():
    plan = BootstrapPlan()
    plan.add(_ok_step("a"))
    with pytest.raises(OfflineBootstrapError, match="duplicate"):
        plan.add(_ok_step("a"))


def test_empty_name_rejected():
    with pytest.raises(OfflineBootstrapError, match="non-empty"):
        BootstrapStep(name="  ", action=lambda ctx: None)


def test_context_artifacts():
    ctx = BootstrapContext()
    ctx.record_artifact("k", {"v": 1})
    assert ctx.artifacts["k"] == {"v": 1}
    assert ctx.get("missing", "dflt") == "dflt"


# --- offline-first law ---------------------------------------------------------------------

def test_validate_offline_rejects_network_steps():
    plan = BootstrapPlan([
        _ok_step("local"),
        BootstrapStep(name="phone-home", action=lambda ctx: None,
                      requires_network=True),
    ])
    with pytest.raises(OfflineBootstrapError,
                       match=r"offline-first violation.*phone-home"):
        plan.validate_offline()
    with pytest.raises(OfflineBootstrapError):
        plan.run()  # run() validates first


def test_default_plan_is_offline_clean(tmp_path):
    plan = default_edge_plan(store_dir=str(tmp_path / "store"))
    plan.validate_offline()  # must not raise
    assert len(plan.steps) == 9


# --- default plan end-to-end ---------------------------------------------------------------------

def test_default_plan_runs_on_this_host(tmp_path):
    meminfo = "MemTotal:        4000000 kB\nMemAvailable:    3000000 kB\n"
    plan = default_edge_plan(
        store_dir=str(tmp_path / "store"),
        probe=PlatformProbe(cpuinfo_text="processor: 0\n"),
        memory=MemoryManager(meminfo_text=meminfo))
    ctx = BootstrapContext()
    outcomes = plan.run(ctx)
    assert plan.succeeded(), [o.to_dict() for o in outcomes]
    # every component the campaign built is now live in the context
    for key in ("platform", "arm64_report", "memory", "memory_mode",
                "wear_store", "npu_registry", "npu_devices",
                "residency", "edge_cache", "thermal_governor"):
        assert ctx.get(key) is not None, key
    assert ctx.artifacts["memory_mode"] in ("standard", "low", "critical")
    ctx.get("wear_store").close()


def test_default_plan_audit_failure_aborts(tmp_path):
    # big-endian host fixture -> audit error -> critical abort
    from hugrgate.edge.platform import PlatformInfo
    info = PlatformInfo(
        arch="aarch64", system="Linux", release="1", python_version=(3, 11, 0),
        python_implementation="CPython", cpu_count=4, cpu_features=(),
        page_size=4096, byteorder="big", is_64bit=True, live=False)
    class BigEndianProbe(PlatformProbe):
        def probe(self):  # type: ignore[override]
            return info
    plan = default_edge_plan(store_dir=str(tmp_path / "store"),
                             probe=BigEndianProbe())
    outcomes = plan.run()
    statuses = [o.status for o in outcomes]
    assert statuses[0] == "ok"          # platform-probe
    assert statuses[1] == "failed"      # arm64-audit (critical)
    assert all(s == "skipped" for s in statuses[2:])
    assert not plan.succeeded()
