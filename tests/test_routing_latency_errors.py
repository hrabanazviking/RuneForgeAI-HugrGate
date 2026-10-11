"""Dawn-forge slice 5 — errors-taxonomy-routing-latency.

``hugrgate/routing/latency.py`` must raise the taxonomy (RoutingError),
never bare stdlib ValueError/KeyError/RuntimeError.
"""

from __future__ import annotations

import pytest

from hugrgate.errors import HugrGateError, RoutingError
from hugrgate.routing.latency import LatencyTracker


def test_alpha_out_of_range_raises_routing_error():
    with pytest.raises(RoutingError) as excinfo:
        LatencyTracker(alpha=0.0)
    assert excinfo.value.code == "routing_error"
    assert excinfo.value.recoverable is False
    assert excinfo.value.details["alpha"] == 0.0


def test_min_samples_below_one_raises_routing_error():
    with pytest.raises(RoutingError) as excinfo:
        LatencyTracker(min_samples=0)
    assert isinstance(excinfo.value, HugrGateError)
    assert excinfo.value.details["min_samples"] == 0


def test_negative_latency_record_raises_routing_error():
    tracker = LatencyTracker()
    with pytest.raises(RoutingError) as excinfo:
        tracker.record("backend-a", -5.0)
    assert excinfo.value.code == "routing_error"
    assert excinfo.value.details["latency_ms"] == -5.0
    assert excinfo.value.details["backend_name"] == "backend-a"


def test_routing_error_wire_round_trip():
    err = RoutingError("alpha must be in (0,1], got 0.0", alpha=0.0)
    clone = HugrGateError.from_dict(err.to_dict())
    assert isinstance(clone, RoutingError)
    assert clone.code == "routing_error"
    assert clone.details == {"alpha": 0.0}


def test_valid_construction_still_works():
    tracker = LatencyTracker(alpha=1.0, min_samples=1)
    tracker.record("backend-a", 12.5)
    assert tracker.measured("backend-a") == 12.5
