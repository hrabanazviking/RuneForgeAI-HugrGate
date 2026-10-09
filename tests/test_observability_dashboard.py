"""Slice 335 — health dashboard data aggregation."""

from __future__ import annotations

import json

import pytest

from hugrgate.errors import MetricError
from hugrgate.health import HealthMonitor
from hugrgate.observability import dashboard
from hugrgate.observability.dashboard import HealthDashboard
from hugrgate.observability.metrics import MetricRegistry


def _sick_dashboard() -> HealthDashboard:
    dash = HealthDashboard(health=HealthMonitor(
        window=50, quarantine_threshold=0.3, max_consecutive_failures=3,
        min_samples=3))
    for _ in range(5):
        dash.observe("good", 10.0, ok=True, verdict="accept")
    for _ in range(4):
        dash.observe("sick", 10.0, ok=False, verdict="accept")
    return dash


def test_snapshot_healthy_when_all_well():
    dash = HealthDashboard()
    for _ in range(5):
        dash.observe("stub", 12.0, ok=True, verdict="accept")
    snap = dash.snapshot()
    assert snap["status"] == "healthy"
    assert snap["totals"]["decisions"] == 5
    assert snap["backends"]["stub"]["quarantined"] is False
    assert snap["backends"]["stub"]["decisions_total"] == 5
    assert snap["backends"]["stub"]["p50_ms"] == pytest.approx(12.0)
    json.dumps(snap)  # JSON-serializable


def test_quarantine_drives_critical_status():
    dash = _sick_dashboard()
    snap = dash.snapshot()
    assert snap["status"] == "critical"
    assert snap["backends"]["sick"]["quarantined"] is True
    assert snap["backends"]["good"]["quarantined"] is False
    assert snap["totals"]["quarantined_backends"] == 1


def test_warning_alert_drives_degraded():
    dash = HealthDashboard()
    dash.observe("stub", 5.0, ok=True)
    snap = dash.snapshot(alerts=[{
        "alert_name": "latency_rising", "severity": "warning"}])
    assert snap["status"] == "degraded"
    assert snap["firing_alerts"][0]["alert_name"] == "latency_rising"


def test_critical_alert_drives_critical():
    dash = HealthDashboard()
    dash.observe("stub", 5.0, ok=True)
    snap = dash.snapshot(alerts=[{
        "alert_name": "backend_down", "severity": "critical"}])
    assert snap["status"] == "critical"


def test_slo_statuses_pass_through():
    dash = HealthDashboard()
    dash.observe("stub", 5.0, ok=True)
    slos = [{"slo_name": "availability", "status": "ok",
             "error_budget_remaining": 0.9}]
    snap = dash.snapshot(slo_statuses=slos)
    assert snap["slos"] == slos


def test_observe_validates_inputs():
    dash = HealthDashboard()
    with pytest.raises(MetricError):
        dash.observe("stub", 5.0, verdict="maybe")
    with pytest.raises(MetricError):
        dash.observe("", 5.0)
    with pytest.raises(MetricError):
        dash.observe("stub", -1.0)


def test_abstention_is_not_a_backend_failure():
    dash = HealthDashboard()
    for _ in range(10):
        dash.observe("stub", 5.0, ok=True, verdict="abstain")
    snap = dash.snapshot()
    assert snap["status"] == "healthy"
    assert snap["backends"]["stub"]["error_rate"] == 0.0


def test_empty_dashboard_snapshot():
    snap = HealthDashboard().snapshot()
    assert snap["status"] == "healthy"
    assert snap["backends"] == {}
    assert snap["totals"]["decisions"] == 0


def test_dashboard_reuses_shared_registry_and_health():
    reg = MetricRegistry()
    health = HealthMonitor()
    dash = HealthDashboard(registry=reg, health=health)
    dash.observe("stub", 5.0, ok=True)
    assert reg.get("hugrgate_decisions_total") is not None
    assert health.stats("stub")["samples"] == 1


def test_dashboard_exports_stay_inside_contract():
    assert set(dashboard.__all__) == {"VERDICTS", "HealthDashboard"}
