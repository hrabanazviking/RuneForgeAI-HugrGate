"""Slice 7 — circuit breaker Prometheus export.

Drives a :class:`hugrgate.circuit.CircuitBreaker` through
closed -> open -> half-open (deterministic injectable clock) and asserts
the exposition carries ``hugrgate_circuit_state`` (gauge,
labels ``backend``; closed=0, open=1, half-open=2) and
``hugrgate_circuit_transitions_total`` (counter, labels
``backend``, ``to_state``).
"""

from __future__ import annotations

from hugrgate.circuit import CircuitRegistry
from hugrgate.observability.metrics import MetricRegistry
from hugrgate.observability.prometheus import (
    CIRCUIT_STATE_GAUGE,
    CIRCUIT_TRANSITIONS_COUNTER,
    CircuitPrometheusExporter,
    generate_latest,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _setup():
    clock = _Clock()
    circuits = CircuitRegistry(failure_threshold=2, reset_timeout_s=30.0,
                               clock=clock)
    exporter = CircuitPrometheusExporter(circuits)
    return clock, circuits, exporter


def _samples(text: str) -> list[str]:
    return [line for line in text.splitlines()
            if line.strip() and not line.startswith("#")]


def test_closed_renders_gauge_zero_with_headers():
    _, circuits, exporter = _setup()
    circuits.get("api")
    out = exporter.render()
    assert "# TYPE hugrgate_circuit_state gauge" in out
    assert "# TYPE hugrgate_circuit_transitions_total counter" in out
    assert f'{CIRCUIT_STATE_GAUGE}{{backend="api"}} 0' in out
    # first sighting is a baseline: no transition counted yet
    assert not any(line.startswith(CIRCUIT_TRANSITIONS_COUNTER + "{")
                   for line in _samples(out))


def test_closed_open_half_open_cycle():
    clock, circuits, exporter = _setup()
    breaker = circuits.get("api")

    out = exporter.render()
    assert f'{CIRCUIT_STATE_GAUGE}{{backend="api"}} 0' in out

    breaker.record_failure()
    out = exporter.render()
    assert f'{CIRCUIT_STATE_GAUGE}{{backend="api"}} 0' in out  # threshold 2

    breaker.record_failure()
    assert breaker.state == "open"
    out = exporter.render()
    samples = _samples(out)
    assert f'{CIRCUIT_STATE_GAUGE}{{backend="api"}} 1' in samples
    assert (f'{CIRCUIT_TRANSITIONS_COUNTER}'
            f'{{backend="api",to_state="open"}} 1') in samples

    clock.now += 31.0
    assert breaker.allow() is True
    assert breaker.state == "half-open"
    out = exporter.render()
    samples = _samples(out)
    assert f'{CIRCUIT_STATE_GAUGE}{{backend="api"}} 2' in samples
    assert (f'{CIRCUIT_TRANSITIONS_COUNTER}'
            f'{{backend="api",to_state="half-open"}} 1') in samples


def test_repeat_scrape_counts_no_spurious_transitions():
    _, circuits, exporter = _setup()
    breaker = circuits.get("api")
    exporter.render()  # baseline: closed, no transition counted
    breaker.record_failure()
    breaker.record_failure()  # -> open
    exporter.render()
    out = exporter.render()
    samples = _samples(out)
    assert (f'{CIRCUIT_TRANSITIONS_COUNTER}'
            f'{{backend="api",to_state="open"}} 1') in samples


def test_generate_latest_wires_circuit_exporter():
    _, circuits, exporter = _setup()
    circuits.get("api")
    exporter.render()
    out = generate_latest(MetricRegistry(), circuit_exporter=exporter)
    assert f'{CIRCUIT_STATE_GAUGE}{{backend="api"}} 0' in out


def test_generate_latest_without_exporter_unchanged():
    out = generate_latest(MetricRegistry())
    assert out == ""
