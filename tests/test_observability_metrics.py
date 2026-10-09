"""Slice 326 — metrics architecture: counters, gauges, histograms, registry.

Covers success paths, validation failures (bad names, bad labels,
negative increments, non-finite observations), boundary behavior
(cardinality cap, conflicting re-registration, empty histogram
percentiles), and thread-safety smoke.
"""

from __future__ import annotations

import threading

import pytest

from hugrgate.errors import MetricError
from hugrgate.observability import metrics
from hugrgate.observability.metrics import (
    Counter,
    MetricRegistry,
    validate_metric_name,
)


def test_validate_metric_name_accepts_prometheus_names():
    assert validate_metric_name("hugrgate_decisions_total") == \
        "hugrgate_decisions_total"
    assert validate_metric_name(":weird_but_legal") == ":weird_but_legal"


def test_validate_metric_name_rejects_bad_names():
    for bad in ("", "1abc", "has space", "has-dash", "ünïcode", 123):
        with pytest.raises(MetricError):
            validate_metric_name(bad)  # type: ignore[arg-type]


def test_counter_inc_and_value():
    reg = MetricRegistry()
    c = reg.counter("decisions_total", "decisions", labels=("backend",))
    c.inc(labels={"backend": "stub"})
    c.inc(2.5, labels={"backend": "stub"})
    assert c.value(labels={"backend": "stub"}) == 3.5


def test_counter_rejects_negative_increment():
    reg = MetricRegistry()
    c = reg.counter("c")
    with pytest.raises(MetricError):
        c.inc(-1.0)


def test_counter_rejects_nan_increment():
    reg = MetricRegistry()
    c = reg.counter("c")
    with pytest.raises(MetricError):
        c.inc(float("nan"))


def test_gauge_set_inc_dec():
    reg = MetricRegistry()
    g = reg.gauge("inflight")
    g.set(5.0)
    g.inc(2.0)
    g.dec(7.0)
    assert g.value() == 0.0


def test_gauge_rejects_nonfinite():
    reg = MetricRegistry()
    g = reg.gauge("g")
    with pytest.raises(MetricError):
        g.set(float("inf"))


def test_histogram_observe_buckets_sum_count():
    reg = MetricRegistry()
    h = reg.histogram("latency_seconds", labels=("backend",),
                      buckets=(0.1, 0.5, 1.0))
    h.observe(0.05, labels={"backend": "a"})
    h.observe(0.3, labels={"backend": "a"})
    h.observe(5.0, labels={"backend": "a"})  # above last bucket
    assert h.buckets(labels={"backend": "a"}) == [1, 1, 0]
    assert h.count(labels={"backend": "a"}) == 3
    assert h.total(labels={"backend": "a"}) == pytest.approx(5.35)


def test_histogram_rejects_bad_buckets():
    reg = MetricRegistry()
    with pytest.raises(MetricError):
        reg.histogram("h1", buckets=())
    with pytest.raises(MetricError):
        reg.histogram("h2", buckets=(0.5, 0.1))
    with pytest.raises(MetricError):
        reg.histogram("h3", buckets=(0.1, 0.1))
    with pytest.raises(MetricError):
        reg.histogram("h4", buckets=(-1.0, 0.1))


def test_histogram_rejects_negative_observation():
    reg = MetricRegistry()
    h = reg.histogram("h")
    with pytest.raises(MetricError):
        h.observe(-0.5)


def test_histogram_percentile_needs_observations():
    reg = MetricRegistry()
    h = reg.histogram("h", buckets=(0.1, 1.0))
    with pytest.raises(MetricError):
        h.percentile(0.5)


def test_histogram_percentile_q_bounds():
    reg = MetricRegistry()
    h = reg.histogram("h", buckets=(0.1, 1.0))
    h.observe(0.05)
    with pytest.raises(MetricError):
        h.percentile(1.5)
    with pytest.raises(MetricError):
        h.percentile(-0.1)


def test_wrong_label_set_raises():
    reg = MetricRegistry()
    c = reg.counter("c", labels=("backend",))
    with pytest.raises(MetricError):
        c.inc(labels={"other": "x"})
    with pytest.raises(MetricError):
        c.inc()  # missing labels
    with pytest.raises(MetricError):
        c.inc(labels={"backend": 123})  # type: ignore[dict-item]


def test_duplicate_metric_name_same_definition_returns_same():
    reg = MetricRegistry()
    c1 = reg.counter("c", labels=("b",))
    c2 = reg.counter("c", labels=("b",))
    assert c1 is c2


def test_conflicting_reregistration_raises():
    reg = MetricRegistry()
    reg.counter("c", labels=("b",))
    with pytest.raises(MetricError):
        reg.gauge("c", labels=("b",))
    with pytest.raises(MetricError):
        reg.counter("c", labels=("other",))


def test_cardinality_cap_is_enforced():
    reg = MetricRegistry(max_series=3)
    c = reg.counter("c", labels=("b",))
    for i in range(3):
        c.inc(labels={"b": f"backend-{i}"})
    with pytest.raises(MetricError):
        c.inc(labels={"b": "backend-overflow"})
    # existing series still record fine
    c.inc(labels={"b": "backend-0"})
    assert c.value(labels={"b": "backend-0"}) == 2.0


def test_registry_rejects_bad_max_series():
    with pytest.raises(MetricError):
        MetricRegistry(max_series=0)


def test_registry_get_and_snapshot():
    reg = MetricRegistry()
    reg.counter("c_total", "a counter", labels=("b",)).inc(
        labels={"b": "x"})
    assert isinstance(reg.get("c_total"), Counter)
    assert reg.get("missing") is None
    snap = reg.snapshot()
    assert snap["metrics"][0]["name"] == "c_total"
    assert snap["metrics"][0]["kind"] == "counter"
    assert snap["metrics"][0]["series"][0]["labels"] == {"b": "x"}
    assert snap["metrics"][0]["series"][0]["value"] == 1.0
    import json
    json.dumps(snap)  # must be JSON-serializable


def test_snapshot_histogram_series():
    reg = MetricRegistry()
    h = reg.histogram("h", buckets=(0.1, 1.0))
    h.observe(0.05)
    snap = reg.snapshot()
    row = snap["metrics"][0]["series"][0]
    assert row["count"] == 1
    assert row["buckets"] == {"0.1": 1, "1.0": 0}


def test_timer_context_manager_observes():
    reg = MetricRegistry()
    h = reg.histogram("lat", buckets=(0.001, 1.0))
    with reg.timer(h):
        pass
    assert h.count() == 1
    assert h.total() >= 0.0


def test_concurrent_increments_are_safe():
    reg = MetricRegistry()
    c = reg.counter("c")
    threads = [threading.Thread(target=lambda: [c.inc() for _ in range(200)])
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert c.value() == 1600.0


def test_metric_module_exports_stay_inside_contract():
    assert set(metrics.__all__) == {
        "DEFAULT_LATENCY_BUCKETS", "Counter", "Gauge", "Histogram",
        "MetricRegistry", "validate_metric_name"}
