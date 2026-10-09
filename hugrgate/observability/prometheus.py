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
"""

from __future__ import annotations

from hugrgate.errors import MetricError
from hugrgate.observability.metrics import MetricRegistry

__all__ = [
    "CONTENT_TYPE",
    "escape_label_value",
    "generate_latest",
]

#: Content-Type for the exposition payload.
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


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


def generate_latest(registry: MetricRegistry) -> str:
    """Render the registry in Prometheus text exposition format."""
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
    return "\n".join(lines)
