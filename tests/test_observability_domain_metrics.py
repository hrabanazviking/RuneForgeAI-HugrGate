"""Slices 338-342 — abstention, escalation, cost, energy, privacy metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hugrgate.abstain import abstain
from hugrgate.errors import (
    DataFlowDenied,
    MetricError,
    SpecError,
)
from hugrgate.observability.abstention import AbstentionMetrics
from hugrgate.observability.cost import CostMetrics
from hugrgate.observability.energy import (
    DefaultEnergyEstimator,
    EnergyMetrics,
)
from hugrgate.observability.escalation import EscalationMetrics
from hugrgate.observability.metrics import MetricRegistry
from hugrgate.observability.privacy_metrics import PrivacyEventMetrics
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec
from hugrgate.supervision import Supervisor


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


def _accept(backend: str = "stub") -> DecisionResult:
    return DecisionResult(value="yes", probability=0.9,
                          distribution={"yes": 0.9, "no": 0.1},
                          backend=backend)


# --- slice 338: abstention metrics ------------------------------------------------


def test_abstention_counted_by_reason():
    metrics = AbstentionMetrics()
    assert metrics.record(abstain(_spec(), reason="below_threshold",
                                  backend="stub")) == "abstain"
    assert metrics.record(abstain(_spec(), reason="policy_veto",
                                  backend="stub")) == "abstain"
    assert metrics.record(_accept()) == "accept"
    by_reason = metrics.abstentions_by_reason()
    assert by_reason == {"below_threshold": 1.0, "policy_veto": 1.0}
    summary = metrics.summary()
    assert summary["decisions_observed"] == 3
    assert summary["abstention_rate_window"] == pytest.approx(2 / 3, abs=1e-4)


def test_review_counted_separately():
    metrics = AbstentionMetrics()
    result = DecisionResult(
        value="yes", probability=0.6,
        distribution={"yes": 0.6, "no": 0.4}, backend="stub",
        metadata={"policy_verdict": "review"})
    assert metrics.record(result) == "review"
    assert metrics.summary()["abstention_rate_window"] == 0.0


def test_abstention_window_is_bounded():
    metrics = AbstentionMetrics(window=10)
    for _ in range(25):
        metrics.record(_accept())
    summary = metrics.summary()
    assert summary["window_size"] == 10
    assert summary["decisions_observed"] == 25


def test_abstention_rejects_bad_window():
    with pytest.raises(MetricError):
        AbstentionMetrics(window=0)


# --- slice 339: escalation metrics -------------------------------------------------


def test_escalation_callback_wiring():
    metrics = EscalationMetrics()
    callback = metrics.as_callback()
    supervisor = Supervisor(check_interval_s=3600, on_escalation=callback)
    supervisor.add_worker("w1", lambda ctx: None, max_restarts=0,
                          restart_window_s=60.0)
    # Force the escalation path directly through the callback contract.
    callback("w1", "restart budget exhausted", None)
    summary = metrics.summary()
    assert summary["total_escalations"] == 1.0
    assert summary["total_restarts"] == 0.0
    events = metrics.recent_escalations()
    assert len(events) == 1
    assert events[0]["worker"] == "w1"
    assert events[0]["reason"] == "restart budget exhausted"
    assert "timestamp" in events[0]


def test_restart_counting_and_validation():
    metrics = EscalationMetrics()
    metrics.record_restart("w1")
    metrics.record_restart("w1")
    assert metrics.restarts("w1") == 2.0
    with pytest.raises(MetricError):
        metrics.record_restart("")
    with pytest.raises(MetricError):
        metrics.record_escalation("w1", "")


def test_escalation_history_bounded_and_newest_first():
    metrics = EscalationMetrics()
    for i in range(5):
        metrics.record_escalation("w", f"reason-{i}")
    events = metrics.recent_escalations(limit=3)
    assert [e["reason"] for e in events] == [
        "reason-4", "reason-3", "reason-2"]
    with pytest.raises(MetricError):
        metrics.recent_escalations(limit=0)


# --- slice 340: cost metrics ---------------------------------------------------------


def test_cost_aggregation():
    metrics = CostMetrics()
    metrics.record(0.01, backend="a", route="ladder")
    metrics.record(0.02, backend="a", route="ladder")
    metrics.record(0.05, backend="b")
    assert metrics.total() == pytest.approx(0.08)
    assert metrics.total(backend="a") == pytest.approx(0.03)
    assert metrics.total(route="ladder") == pytest.approx(0.03)
    summary = metrics.summary()
    assert summary["currency"] == "USD"
    assert summary["total"] == pytest.approx(0.08)
    assert summary["by_backend"] == {"a": 0.03, "b": 0.05}


def test_cost_rejects_negative_and_bad_inputs():
    metrics = CostMetrics()
    with pytest.raises(MetricError):
        metrics.record(-0.01, backend="a")
    with pytest.raises(MetricError):
        metrics.record(float("nan"), backend="a")
    with pytest.raises(MetricError):
        metrics.record(0.01, backend="")
    with pytest.raises(MetricError):
        CostMetrics(currency="")


def test_cost_ledger_newest_first():
    metrics = CostMetrics()
    metrics.record(0.01, backend="a")
    metrics.record(0.02, backend="b")
    charges = metrics.recent_charges(limit=2)
    assert [c["backend"] for c in charges] == ["b", "a"]
    assert charges[0]["currency"] == "USD"


# --- slice 341: energy metrics ----------------------------------------------------------


def test_energy_estimator_math():
    estimator = DefaultEnergyEstimator()
    # 250 W for 3.6 s (3600 ms) == 0.25 Wh.
    assert estimator.estimate_wh("gpu", 3600.0) == pytest.approx(0.25)
    assert estimator.estimate_wh("mystery", 3600.0) == pytest.approx(
        65.0 * 3600.0 / 3_600_000.0)
    with pytest.raises(MetricError):
        estimator.estimate_wh("gpu", -1.0)
    with pytest.raises(MetricError):
        DefaultEnergyEstimator(power_w={"gpu": -5.0})
    description = estimator.describe()
    assert description["model"] == "power_coefficient"
    assert "caveat" in description


def test_energy_metrics_record_and_total():
    metrics = EnergyMetrics()
    recorded = metrics.record("gpu", 3600.0)
    assert recorded == pytest.approx(0.25)
    metrics.record("cpu", 3600.0, energy_wh=0.1)  # metered override wins
    assert metrics.total_wh() == pytest.approx(0.35)
    assert metrics.total_wh(backend="gpu") == pytest.approx(0.25)
    summary = metrics.summary()
    assert summary["total_wh"] == pytest.approx(0.35)
    assert summary["estimator"]["model"] == "power_coefficient"


def test_energy_rejects_bad_values():
    metrics = EnergyMetrics()
    with pytest.raises(MetricError):
        metrics.record("", 10.0)
    with pytest.raises(MetricError):
        metrics.record("gpu", 10.0, energy_wh=-0.1)


def test_energy_artifact_is_honest():
    artifact_path = Path(__file__).resolve().parent.parent / "benchmarks" \
        / "observability_energy_341.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["slice"] == 341
    assert artifact["determinism_check"]["deterministic"] is True
    assert "NOT a meter reading" in json.dumps(artifact)
    assert artifact["model"]["model"] == "power_coefficient"


# --- slice 342: privacy-event metrics -----------------------------------------------------


def test_privacy_violations_counted_by_code():
    metrics = PrivacyEventMetrics()
    metrics.record_violation(DataFlowDenied("blocked"), "strict")
    metrics.record_violation(DataFlowDenied("blocked again"), "strict")
    summary = metrics.summary()
    assert summary["by_violation_code"] == {"data_flow_denied": 2.0}
    assert summary["totals"]["hugrgate_privacy_violations_total"] == 2.0


def test_privacy_denied_flows_and_redactions():
    metrics = PrivacyEventMetrics()
    metrics.record_denied_flow("gpu", "strict")
    metrics.record_redaction("gpu")
    summary = metrics.summary()
    assert summary["totals"]["hugrgate_privacy_denied_flows_total"] == 1.0
    assert summary["totals"]["hugrgate_privacy_redactions_total"] == 1.0


def test_privacy_record_violation_rejects_non_violations():
    metrics = PrivacyEventMetrics()
    with pytest.raises(MetricError):
        metrics.record_violation(SpecError("not privacy"))  # type: ignore[arg-type]


def test_privacy_adversarial_label_smuggling_rejected():
    # Adversarial: try to smuggle payload through label names/values.
    from hugrgate.observability import privacy_metrics as pm
    with pytest.raises(MetricError):
        pm._scrub_labels({"value": "the-secret-decision"})
    with pytest.raises(MetricError):
        pm._scrub_labels({"state": "full-state-dump"})
    with pytest.raises(MetricError):
        pm._scrub_labels({"backend": "x" * 500})
    with pytest.raises(MetricError):
        pm._scrub_labels({"violation_code": 123})  # type: ignore[dict-item]
    # And the allowlist itself contains no payload key.
    assert not (pm._ALLOWED_LABELS & {
        "state", "value", "input", "prompt", "payload", "pii"})


def test_privacy_metrics_share_registry():
    reg = MetricRegistry()
    PrivacyEventMetrics(registry=reg)
    assert reg.get("hugrgate_privacy_violations_total") is not None
