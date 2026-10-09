"""Slices 329-332 — decision, backend, routing, calibration trace spans."""

from __future__ import annotations

import random

import pytest

from hugrgate.abstain import abstain
from hugrgate.adaptive.telemetry import RouteEvent
from hugrgate.errors import TraceError
from hugrgate.observability.spans_backend import (
    BACKEND_SPAN_NAME,
    annotate_backend_outcome,
    backend_span,
)
from hugrgate.observability.spans_calibration import (
    CALIBRATION_SPAN_NAME,
    annotate_calibration,
    calibration_span,
    coverage_within_tolerance,
    empirical_coverage,
)
from hugrgate.observability.spans_decision import (
    DECISION_SPAN_NAME,
    annotate_decision,
    decision_span,
    probability_band,
    verdict_of,
)
from hugrgate.observability.spans_routing import (
    ROUTING_SPAN_NAME,
    annotate_routing,
    routing_span,
)
from hugrgate.observability.trace import Tracer
from hugrgate.policy import DecisionPolicy
from hugrgate.result import DecisionResult
from hugrgate.spec import DecisionSpec


def _spec() -> DecisionSpec:
    return DecisionSpec(type="categorical", options=["yes", "no"])


def _result(**over: object) -> DecisionResult:
    base: dict = {
        "value": "yes", "probability": 0.93,
        "distribution": {"yes": 0.93, "no": 0.07},
        "backend": "stub", "model": "m", "latency_ms": 12.5,
    }
    base.update(over)
    return DecisionResult(**base)


def _route_event() -> RouteEvent:
    return RouteEvent(
        request_id="r1", timestamp=1.0, spec={"type": "categorical"},
        features={"f": 1.0}, candidates=["a", "b"],
        propensities={"a": 0.7, "b": 0.3}, chosen="a",
        policy_version="v3", privacy_class="standard",
        latency_ms=2.0, cost=0.01, energy_wh=0.001,
    )


# --- slice 329: decision spans ------------------------------------------------


def test_probability_band_edges():
    assert probability_band(0.0) == "0.0-0.1"
    assert probability_band(0.95) == "0.9-1.0"
    assert probability_band(1.0) == "0.9-1.0"
    with pytest.raises(TraceError):
        probability_band(1.5)


def test_verdict_of():
    assert verdict_of(_result()) == "accept"
    review = _result(metadata={"policy_verdict": "review"})
    assert verdict_of(review) == "review"
    assert verdict_of(abstain(_spec(), reason="below_threshold")) == "abstain"


def test_decision_span_nests_and_annotates():
    tracer = Tracer()
    policy = DecisionPolicy(minimum_probability=0.8)
    with tracer.trace("root"):
        with decision_span(tracer, _spec(), policy) as span:
            assert span.parent_span_id is not None
            annotate_decision(span, _spec(), _result(), policy)
    spans = tracer.store.find_spans(DECISION_SPAN_NAME)
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["decision.spec_type"] == "categorical"
    assert attrs["decision.verdict"] == "accept"
    assert attrs["decision.probability_band"] == "0.9-1.0"
    assert attrs["decision.policy_min_probability"] == 0.8
    assert attrs["decision.policy_privacy_class"] == "standard"
    # payload stays out of spans
    assert "decision.value" not in attrs
    assert not any("distribution" in k for k in attrs)
    events = [e["name"] for e in spans[0].events]
    assert "decision.accept" in events


def test_decision_span_abstention_path():
    tracer = Tracer()
    with decision_span(tracer, _spec()) as span:
        annotate_decision(span, _spec(),
                          abstain(_spec(), reason="below_threshold"))
    spans = tracer.store.find_spans(DECISION_SPAN_NAME)
    assert spans[0].attributes["decision.verdict"] == "abstain"
    events = {e["name"]: e for e in spans[0].events}
    assert "decision.abstain" in events
    assert events["decision.abstain_reason"]["attributes"]["reason"] == \
        "below_threshold"


# --- slice 330: backend spans -------------------------------------------------


def test_backend_span_success_records_latency():
    tracer = Tracer()
    with backend_span(tracer, "stub", attempt=1):
        pass
    spans = tracer.store.find_spans(BACKEND_SPAN_NAME)
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["backend.name"] == "stub"
    assert attrs["backend.attempt"] == 1
    assert attrs["backend.ok"] is True
    assert attrs["backend.latency_ms"] >= 0.0
    assert spans[0].status == "ok"


def test_backend_span_taxonomy_error_recorded():
    from hugrgate.errors import BackendUnavailable
    tracer = Tracer()
    with pytest.raises(BackendUnavailable):
        with backend_span(tracer, "gpu", attempt=2):
            raise BackendUnavailable("down")
    spans = tracer.store.find_spans(BACKEND_SPAN_NAME)
    attrs = spans[0].attributes
    assert attrs["backend.ok"] is False
    assert attrs["backend.error_code"] == "backend_unavailable"
    assert attrs["backend.attempt"] == 2
    assert spans[0].status == "error: backend_unavailable"


def test_backend_span_stdlib_error_uses_type_name():
    tracer = Tracer()
    with pytest.raises(RuntimeError):
        with backend_span(tracer, "stub"):
            raise RuntimeError("weird")
    spans = tracer.store.find_spans(BACKEND_SPAN_NAME)
    assert spans[0].attributes["backend.error_code"] == "RuntimeError"


def test_backend_span_rejects_bad_attempt():
    tracer = Tracer()
    with pytest.raises(TraceError):
        with backend_span(tracer, "stub", attempt=0):
            pass


def test_annotate_backend_outcome_direct():
    tracer = Tracer()
    with tracer.trace("s") as span:
        annotate_backend_outcome(span, "stub", 3.25, True)
        assert span.attributes["backend.latency_ms"] == 3.25


# --- slice 331: routing spans -------------------------------------------------


def test_routing_span_from_route_event():
    tracer = Tracer()
    with routing_span(tracer, _route_event()):
        pass
    spans = tracer.store.find_spans(ROUTING_SPAN_NAME)
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["routing.chosen"] == "a"
    assert attrs["routing.candidate_count"] == 2
    assert attrs["routing.propensity"] == pytest.approx(0.7)
    assert attrs["routing.policy_version"] == "v3"
    assert attrs["routing.shadow"] is False
    assert attrs["routing.latency_ms"] == pytest.approx(2.0)


def test_routing_span_from_plain_mapping():
    tracer = Tracer()
    with tracer.trace("s") as span:
        annotate_routing(span, {
            "candidates": ["x", "y"], "chosen": "y",
            "propensities": {"x": 0.2, "y": 0.8},
        })
        assert span.attributes["routing.chosen"] == "y"


def test_routing_span_rejects_inconsistent_event():
    tracer = Tracer()
    with tracer.trace("s") as span:
        with pytest.raises(TraceError):
            annotate_routing(span, {"candidates": ["x"], "chosen": "z"})
        with pytest.raises(TraceError):
            annotate_routing(span, {"candidates": [], "chosen": "x"})
        with pytest.raises(TraceError):
            annotate_routing(span, "not-an-event")  # type: ignore[arg-type]


# --- slice 332: calibration spans ----------------------------------------------


def test_empirical_coverage_controlled():
    rng = random.Random(42)
    n = 2000
    sets, truths = [], []
    for i in range(n):
        truth = f"class-{i % 5}"
        if rng.random() < 0.9:
            sets.append([truth, "decoy"])
        else:
            sets.append(["decoy"])
        truths.append(truth)
    achieved = empirical_coverage(sets, truths)
    assert achieved == pytest.approx(0.9, abs=0.03)
    verdict = coverage_within_tolerance(achieved, 0.9, n)
    assert verdict["within_tolerance"] is True
    assert verdict["ci_lower"] <= 0.9 <= verdict["ci_upper"]
    assert verdict["n"] == n


def test_empirical_coverage_detects_miscalibration():
    verdict = coverage_within_tolerance(0.5, 0.9, 2000)
    assert verdict["within_tolerance"] is False


def test_empirical_coverage_validation_errors():
    with pytest.raises(TraceError):
        empirical_coverage([], [])
    with pytest.raises(TraceError):
        empirical_coverage([["a"]], ["a", "b"])
    with pytest.raises(TraceError):
        empirical_coverage([[]], ["a"])
    with pytest.raises(TraceError):
        coverage_within_tolerance(0.9, 1.5, 100)
    with pytest.raises(TraceError):
        coverage_within_tolerance(0.9, 0.9, 0)


def test_calibration_span_annotates():
    tracer = Tracer()
    with calibration_span(tracer, "conformal") as span:
        annotate_calibration(span, "conformal", 0.9, 2000,
                             achieved_coverage=0.91,
                             extra={"alpha": 0.1})
    spans = tracer.store.find_spans(CALIBRATION_SPAN_NAME)
    attrs = spans[0].attributes
    assert attrs["calibration.method"] == "conformal"
    assert attrs["calibration.nominal_coverage"] == 0.9
    assert attrs["calibration.n_samples"] == 2000
    assert attrs["calibration.achieved_coverage"] == 0.91
    assert attrs["calibration.alpha"] == 0.1
    events = {e["name"]: e for e in spans[0].events}
    assert events["calibration.coverage_checked"]["attributes"][
        "within_tolerance"] is True


def test_calibration_span_rejects_bad_inputs():
    tracer = Tracer()
    with tracer.trace("s") as span:
        with pytest.raises(TraceError):
            annotate_calibration(span, "", 0.9, 100)
        with pytest.raises(TraceError):
            annotate_calibration(span, "m", 1.5, 100)
        with pytest.raises(TraceError):
            annotate_calibration(span, "m", 0.9, 0)
