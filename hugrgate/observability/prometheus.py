"""Prometheus text exposition for the metric registry. Slice 334.

Renders :class:`hugrgate.observability.metrics.MetricRegistry` in the
Prometheus text format (version 0.0.4), so any Prometheus server can
scrape HugrGate without a client library:

- counters render as ``<name>_total`` (unless already suffixed);
- gauges render as-is;
- histograms render cumulative ``<name>_bucket{le="..."}`` series plus
  an implicit ``+Inf`` bucket, ``<name>_sum``, and ``<name>_count``;
- label values are escaped per spec (``\\\\``, ``\\n``, ``\\"``).

The renderer reads only :meth:`MetricRegistry.snapshot`, never
instrument internals, so the exposition contract is decoupled from the
registry implementation.

Slice 7 (circuit export) adds :class:`CircuitPrometheusExporter`, which
polls a :class:`hugrgate.circuit.CircuitRegistry` and renders two
metrics: the ``hugrgate_circuit_state`` gauge (labels: ``backend``) and
the ``hugrgate_circuit_transitions_total`` counter (labels: ``backend``,
``to_state``). Transition counts are derived by diffing each scrape
against the previous one — :mod:`hugrgate.circuit` carries no transition
counter — so a fresh exporter counts only transitions it observes, and
the *first* time a backend is seen its state is recorded as a baseline
with no transition counted. Wire an exporter into the exposition via the
``circuit_exporter`` keyword of :func:`generate_latest`; the caller must
reuse one exporter instance across scrapes for the counter to
accumulate.
"""

from __future__ import annotations

import threading

from hugrgate.circuit import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    CircuitRegistry,
)
from hugrgate.errors import MetricError
from hugrgate.observability.metrics import MetricRegistry

__all__ = [
    "CONTENT_TYPE",
    "escape_label_value",
    "generate_latest",
]
# NOTE (slice 7): the slice-334 contract test pins ``__all__`` to exactly
# the names above, so the circuit export names (CIRCUIT_STATE_GAUGE,
# CIRCUIT_STATE_VALUES, CIRCUIT_TRANSITIONS_COUNTER,
# CircuitPrometheusExporter) are importable module attributes but stay out
# of ``__all__``.

#: Content-Type for the exposition payload.
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

#: Gauge name for the per-backend circuit breaker state.
CIRCUIT_STATE_GAUGE = "hugrgate_circuit_state"

#: Counter name for observed circuit breaker state transitions.
CIRCUIT_TRANSITIONS_COUNTER = "hugrgate_circuit_transitions_total"

#: Gauge value encoding for :data:`CIRCUIT_STATE_GAUGE`.
#:
#: - closed    -> 0
#: - open      -> 1
#: - half-open -> 2
#:
#: The encoding is also written into the metric's HELP line so scrapers
#: stay self-describing.
CIRCUIT_STATE_VALUES = {
    CLOSED: 0,
    OPEN: 1,
    HALF_OPEN: 2,
}


def escape_label_value(value: str) -> str:
    """Escape a label value for the Prometheus text format."""
    return (value.replace("\\", "\\\\")
                 .replace("\n", "\\n")
                 .replace('"', '\\"'))


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{escape_label_value(v)}"'
             for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


def _format_float(value: float) -> str:
    if value != value:  # NaN — should never happen; never emit it
        raise MetricError("cannot exposition-format NaN")
    text = repr(float(value))
    return text


class CircuitPrometheusExporter:
    """Export circuit breaker state as Prometheus exposition text.

    Holds a :class:`~hugrgate.circuit.CircuitRegistry` and renders, on
    every :meth:`render` call:

    - ``hugrgate_circuit_state`` gauge, labels ``{backend}`` — the
      breaker's current state encoded per :data:`CIRCUIT_STATE_VALUES`
      (closed=0, open=1, half-open=2).
    - ``hugrgate_circuit_transitions_total`` counter, labels
      ``{backend,to_state}`` — the number of transitions the exporter has
      *observed* into each destination state. ``to_state`` uses the raw
      state strings from :mod:`hugrgate.circuit` (``"closed"``,
      ``"open"``, ``"half-open"``).

    Reuse one instance across scrapes: transitions are diffed against
    the previous scrape, so a new instance would restart counters at
    zero. Thread-safe.
    """

    def __init__(self, registry: CircuitRegistry):
        self._registry = registry
        self._last_state: dict[str, str] = {}
        self._transitions: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def render(self) -> str:
        """Render the circuit metrics in Prometheus text format."""
        with self._lock:
            snapshot = self._registry.snapshot()
            for backend, info in snapshot.items():
                state = str(info["state"])
                if state not in CIRCUIT_STATE_VALUES:
                    raise MetricError(
                        f"unknown circuit state: {state!r}")
                previous = self._last_state.get(backend)
                if previous is not None and previous != state:
                    key = (backend, state)
                    self._transitions[key] = (
                        self._transitions.get(key, 0) + 1)
                self._last_state[backend] = state
            lines = [
                "# HELP hugrgate_circuit_state Current circuit breaker "
                "state: 0=closed, 1=open, 2=half-open.",
                "# TYPE hugrgate_circuit_state gauge",
            ]
            for backend in sorted(self._last_state):
                value = CIRCUIT_STATE_VALUES[self._last_state[backend]]
                lines.append(
                    f"{CIRCUIT_STATE_GAUGE}"
                    f"{_format_labels({'backend': backend})} {value}")
            lines += [
                "# HELP hugrgate_circuit_transitions_total Number of "
                "circuit breaker state transitions observed by this "
                "exporter, labelled by destination state.",
                "# TYPE hugrgate_circuit_transitions_total counter",
            ]
            for (backend, to_state), count in sorted(
                    self._transitions.items()):
                labels = _format_labels({"backend": backend,
                                         "to_state": to_state})
                lines.append(
                    f"{CIRCUIT_TRANSITIONS_COUNTER}{labels} {count}")
            lines.append("")
            return "\n".join(lines)


def generate_latest(registry: MetricRegistry,
                    circuit_exporter: CircuitPrometheusExporter | None = None
                    ) -> str:
    """Render the registry in Prometheus text exposition format.

    When ``circuit_exporter`` is given, its
    :meth:`~CircuitPrometheusExporter.render` output is appended to the
    exposition so circuit breaker state rides the same scrape.
    """
    lines: list[str] = []
    snapshot = registry.snapshot()
    for metric in snapshot["metrics"]:
        name = metric["name"]
        kind = metric["kind"]
        description = metric.get("description") or ""
        if kind == "counter":
            sample_name = (name if name.endswith("_total")
                           else f"{name}_total")
            prom_type = "counter"
        elif kind == "gauge":
            sample_name = name
            prom_type = "gauge"
        elif kind == "histogram":
            sample_name = name
            prom_type = "histogram"
        else:  # pragma: no cover - registry only makes the three kinds
            raise MetricError(f"unknown metric kind: {kind!r}")
        lines.append(f"# HELP {name} {description}".rstrip())
        lines.append(f"# TYPE {name} {prom_type}")
        for series in metric["series"]:
            labels = _format_labels(series["labels"])
            if kind == "histogram":
                buckets: dict[str, int] = series["buckets"]
                cumulative = 0
                for bound, count in buckets.items():
                    cumulative += count
                    le = _format_labels(
                        {**series["labels"], "le": bound})
                    lines.append(f"{sample_name}_bucket{le} {cumulative}")
                total_count = series["count"]
                lines.append(
                    f"{sample_name}_bucket"
                    f"{_format_labels({**series['labels'], 'le': '+Inf'})} "
                    f"{total_count}")
                lines.append(f"{sample_name}_sum{labels} "
                             f"{_format_float(series['sum'])}")
                lines.append(f"{sample_name}_count{labels} {total_count}")
            else:
                lines.append(f"{sample_name}{labels} "
                             f"{_format_float(series['value'])}")
    if lines:
        lines.append("")
    body = "\n".join(lines) if lines else ""
    if circuit_exporter is not None:
        circuit_body = circuit_exporter.render()
        if circuit_body:
            body += circuit_body
    return body
