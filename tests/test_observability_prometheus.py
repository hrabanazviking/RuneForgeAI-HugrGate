"""Slice 334 — Prometheus exposition rendering."""

from __future__ import annotations

import pytest

from hugrgate.errors import MetricError
from hugrgate.observability import prometheus
from hugrgate.observability.metrics import MetricRegistry
from hugrgate.observability.prometheus import (
    CONTENT_TYPE,
    escape_label_value,
    generate_latest,
)


def test_empty_registry_renders_empty():
    assert generate_latest(MetricRegistry()) == ""


def test_counter_gets_total_suffix():
    reg = MetricRegistry()
    reg.counter("decisions", "decision count", labels=("backend",)).inc(
        3, labels={"backend": "stub"})
    out = generate_latest(reg)
    assert "# HELP decisions decision count" in out
    assert "# TYPE decisions counter" in out
    assert 'decisions_total{backend="stub"} 3.0' in out


def test_counter_already_suffixed_not_doubled():
    reg = MetricRegistry()
    reg.counter("decisions_total").inc(2)
    out = generate_latest(reg)
    assert "decisions_total_total" not in out
    assert "decisions_total 2.0" in out


def test_gauge_renders_plain():
    reg = MetricRegistry()
    reg.gauge("inflight", "in flight").set(7)
    out = generate_latest(reg)
    assert "# TYPE inflight gauge" in out
    assert "inflight 7.0" in out


def test_histogram_buckets_are_cumulative_with_inf():
    reg = MetricRegistry()
    h = reg.histogram("latency_seconds", labels=("b",),
                      buckets=(0.1, 0.5))
    h.observe(0.05, labels={"b": "x"})
    h.observe(0.3, labels={"b": "x"})
    h.observe(5.0, labels={"b": "x"})
    out = generate_latest(reg)
    assert "# TYPE latency_seconds histogram" in out
    assert 'latency_seconds_bucket{b="x",le="0.1"} 1' in out
    assert 'latency_seconds_bucket{b="x",le="0.5"} 2' in out
    assert 'latency_seconds_bucket{b="x",le="+Inf"} 3' in out
    assert 'latency_seconds_sum{b="x"} 5.35' in out
    assert 'latency_seconds_count{b="x"} 3' in out


def test_label_escaping():
    assert escape_label_value('a"b\\c\nd') == 'a\\"b\\\\c\\nd'
    reg = MetricRegistry()
    reg.counter("c", labels=("note",)).inc(
        labels={"note": 'say "hi"\nbye\\'})
    out = generate_latest(reg)
    assert 'c_total{note="say \\"hi\\"\\nbye\\\\"} 1.0' in out


def test_nan_series_refused():
    reg = MetricRegistry()
    g = reg.gauge("g")
    # bypass the public setter (which rejects NaN) to simulate a
    # corrupted series, then prove the exporter refuses to emit it.
    g._series[()] = [float("nan")]
    with pytest.raises(MetricError):
        generate_latest(reg)


def test_content_type_constant():
    assert CONTENT_TYPE.startswith("text/plain")


def test_prometheus_exports_stay_inside_contract():
    assert set(prometheus.__all__) == {
        "CONTENT_TYPE", "escape_label_value", "generate_latest"}
