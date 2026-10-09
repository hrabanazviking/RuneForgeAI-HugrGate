"""Slices 343-345 — drift alerts, SLO definitions, SLO evaluator."""

from __future__ import annotations

import pytest

from hugrgate.drift import DriftReport
from hugrgate.errors import AlertError, SLOError
from hugrgate.observability.alerts import (
    Alert,
    AlertManager,
    AlertRule,
    alert_for_drift_report,
)
from hugrgate.observability.slo import SLODefinition
from hugrgate.observability.slo_eval import SLOEvaluator


def _drift_report(severity: str, psi: float = 0.3) -> DriftReport:
    return DriftReport(psi=psi, alert=severity != "none",
                       severity=severity, n_reference=1000, n_live=1000,
                       n_bins=10)


# --- slice 343: drift alerts -------------------------------------------------------


def test_drift_report_maps_to_alert():
    alert = alert_for_drift_report(_drift_report("action", psi=0.42))
    assert alert is not None
    assert alert.severity == "critical"
    assert alert.dedup_key == "drift:drift:action"
    assert "0.420" in alert.message
    assert alert.details["psi"] == pytest.approx(0.42)

    watch = alert_for_drift_report(_drift_report("watch", psi=0.15))
    assert watch is not None and watch.severity == "warning"

    assert alert_for_drift_report(_drift_report("none", psi=0.01)) is None


def test_drift_report_rejects_unknown_severity():
    with pytest.raises(AlertError):
        alert_for_drift_report(_drift_report("meltdown"))


def test_alert_validation():
    with pytest.raises(AlertError):
        Alert(name="", severity="warning", dedup_key="k", message="m")
    with pytest.raises(AlertError):
        Alert(name="n", severity="extreme", dedup_key="k", message="m")
    with pytest.raises(AlertError):
        Alert(name="n", severity="warning", dedup_key="", message="m")


def test_rule_cooldown_dedups_and_counts():
    manager = AlertManager()
    manager.add_rule(AlertRule(
        name="psi_high", severity="critical",
        condition=lambda ctx: ctx.get("psi", 0.0) > 0.25,
        cooldown_s=3600.0))
    first = manager.evaluate({"psi": 0.5})
    assert len(first) == 1
    assert first[0].severity == "critical"
    # Re-fires inside cooldown: suppressed and counted.
    assert manager.evaluate({"psi": 0.9}) == []
    assert manager.suppressed_counts() == {"psi_high": 1}
    # Condition false: nothing happens.
    assert manager.evaluate({"psi": 0.1}) == []


def test_rule_condition_exceptions_abort():
    manager = AlertManager()
    def _boom(ctx):
        raise RuntimeError("broken")
    manager.add_rule(AlertRule(name="broken", severity="warning",
                               condition=_boom))
    with pytest.raises(AlertError, match="broken"):
        manager.evaluate({})


def test_rule_management_validation():
    manager = AlertManager()
    rule = AlertRule(name="r", severity="info", condition=lambda ctx: True)
    manager.add_rule(rule)
    with pytest.raises(AlertError):
        manager.add_rule(rule)  # duplicate
    with pytest.raises(AlertError):
        manager.remove_rule("missing")
    with pytest.raises(AlertError):
        AlertRule(name="x", severity="info", condition="not-callable",  # type: ignore[arg-type]
                  cooldown_s=-1.0)
    with pytest.raises(AlertError):
        AlertManager(max_history=0)


def test_fire_primitive_with_cooldown():
    manager = AlertManager()
    alert = Alert(name="n", severity="warning", dedup_key="k", message="m")
    assert manager.fire(alert, cooldown_s=3600.0) is alert
    assert manager.fire(alert, cooldown_s=3600.0) is None
    assert manager.suppressed_counts() == {"k": 1}
    history = manager.history()
    assert len(history) == 1 and history[0].dedup_key == "k"


def test_evaluate_drift_end_to_end():
    manager = AlertManager()
    fired = manager.evaluate_drift(_drift_report("action", psi=0.5))
    assert fired is not None and fired.severity == "critical"
    # Second report inside cooldown: suppressed.
    assert manager.evaluate_drift(_drift_report("action", psi=0.6)) is None
    assert manager.evaluate_drift(_drift_report("none")) is None


# --- slice 344: SLO definitions ------------------------------------------------------


def test_slo_definition_validates():
    slo = SLODefinition(name="availability", target=0.999, window_s=3600.0)
    assert slo.error_budget == pytest.approx(0.001)
    assert slo.kind == "availability"
    with pytest.raises(SLOError):
        SLODefinition(name="", target=0.99, window_s=60.0)
    with pytest.raises(SLOError):
        SLODefinition(name="x", target=1.5, window_s=60.0)
    with pytest.raises(SLOError):
        SLODefinition(name="x", target=0.0, window_s=60.0)
    with pytest.raises(SLOError):
        SLODefinition(name="x", target=0.99, window_s=0.0)
    with pytest.raises(SLOError):
        SLODefinition(name="x", target=0.99, window_s=60.0, kind="vibes")
    with pytest.raises(SLOError):
        SLODefinition(name="lat", target=0.99, window_s=60.0, kind="latency")


def test_slo_latency_requires_budget_param():
    slo = SLODefinition(name="lat", target=0.99, window_s=60.0,
                        kind="latency",
                        params={"latency_budget_ms": 100.0})
    assert slo.params["latency_budget_ms"] == 100.0


def test_slo_serialization_round_trip():
    slo = SLODefinition(name="avail", target=0.999, window_s=3600.0,
                        description="stay up",
                        params={"team": "gate"})
    rebuilt = SLODefinition.from_dict(slo.to_dict())
    assert rebuilt == slo
    with pytest.raises(SLOError):
        SLODefinition.from_dict({"name": "broken"})
    with pytest.raises(SLOError):
        SLODefinition.from_dict({"name": "x", "target": "high",
                                 "window_s": 60.0})


# --- slice 345: SLO evaluator -----------------------------------------------------------


def _outcomes(n_good: int, n_bad: int, now: float = 1000.0):
    return ([(now - 10.0, True)] * n_good
            + [(now - 10.0, False)] * n_bad)


def test_slo_evaluator_ok():
    evaluator = SLOEvaluator(now=1000.0)
    slo = SLODefinition(name="avail", target=0.99, window_s=3600.0)
    status = evaluator.evaluate_availability(slo, _outcomes(995, 5))
    assert status.status == "ok"
    assert status.good_fraction == pytest.approx(0.995)
    assert status.burn_rate == pytest.approx(0.5)
    assert status.n_samples == 1000
    assert status.to_dict()["status"] == "ok"


def test_slo_evaluator_warning_and_breach():
    evaluator = SLOEvaluator(now=1000.0)
    slo = SLODefinition(name="avail", target=0.99, window_s=3600.0)
    # bad rate 1.5% vs budget 1% -> burn rate 1.5 -> warning.
    warning = evaluator.evaluate_availability(slo, _outcomes(985, 15))
    assert warning.status == "warning"
    assert warning.burn_rate == pytest.approx(1.5)
    # bad rate 5% -> burn rate 5 -> breaching.
    breach = evaluator.evaluate_availability(slo, _outcomes(950, 50))
    assert breach.status == "breaching"
    assert breach.error_budget_remaining == 0.0


def test_slo_evaluator_window_filters_old_samples():
    evaluator = SLOEvaluator(now=1000.0)
    slo = SLODefinition(name="avail", target=0.99, window_s=60.0)
    samples = [(1000.0 - 10.0, True)] * 99 + [(1000.0 - 10.0, False)]
    samples += [(1000.0 - 3600.0, False)] * 500  # outside the window
    status = evaluator.evaluate_availability(slo, samples)
    assert status.n_samples == 100
    assert status.status == "ok"


def test_slo_evaluator_empty_window_raises():
    evaluator = SLOEvaluator(now=1000.0)
    slo = SLODefinition(name="avail", target=0.99, window_s=60.0)
    with pytest.raises(SLOError, match="no samples"):
        evaluator.evaluate_availability(slo, [])


def test_slo_evaluator_latency_kind():
    evaluator = SLOEvaluator(now=1000.0)
    slo = SLODefinition(name="lat", target=0.95, window_s=3600.0,
                        kind="latency",
                        params={"latency_budget_ms": 100.0})
    samples = ([(990.0, 50.0)] * 96 + [(990.0, 500.0)] * 4)
    status = evaluator.evaluate_latency(slo, samples)
    assert status.status == "ok"
    assert status.good_fraction == pytest.approx(0.96)
    with pytest.raises(SLOError):
        evaluator.evaluate_latency(
            SLODefinition(name="a", target=0.99, window_s=60.0), samples)
