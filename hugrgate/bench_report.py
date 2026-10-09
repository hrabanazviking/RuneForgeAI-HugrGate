"""Benchmark report — markdown rendering of benchmark JSON. Slice 47.

Produces a human-readable report with:

- summary + per-backend metric tables,
- ASCII reliability diagrams (accuracy vs confidence per bin),
- a hardware / methodology block for reproducibility.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metric_table(backends: Mapping[str, Mapping[str, Any]]) -> str:
    header = ("| backend | n | accuracy | brier | ece | "
              "p50 (ms) | p99 (ms) | throughput (/s) | abstain |")
    sep = ("|---|---|---|---|---|---|---|---|---|")
    rows = [header, sep]
    for name, m in backends.items():
        rows.append(
            f"| {name} | {m['n_decided']} | {_fmt(m['accuracy'])} | "
            f"{_fmt(m['brier_score'])} | {_fmt(m['ece'])} | "
            f"{_fmt(m['latency_p50_ms'], 1)} | {_fmt(m['latency_p99_ms'], 1)} | "
            f"{_fmt(m['throughput_per_s'], 1)} | {_fmt(m['abstention_rate'])} |")
    return "\n".join(rows)


def ascii_reliability_diagram(bins: List[Mapping[str, Any]],
                              width: int = 30) -> str:
    """Render reliability bins as ASCII: accuracy bars vs confidence marks.

    Each bin shows the confidence interval, a bar of ``#`` scaled to the
    bin's accuracy, a ``|`` marker at the bin's average confidence, and
    the sample count. Perfect calibration = ``|`` at the bar's tip.
    """
    lines = ["```",
             "conf      accuracy vs confidence (n)   ",
             "----------------------------------------"]
    for b in bins:
        n = b["count"]
        if n == 0:
            bar = "(empty)".ljust(width)
            conf_mark = ""
        else:
            filled = int(round(b["accuracy"] * width))
            bar = ("#" * filled).ljust(width)
            pos = min(int(round(b["avg_confidence"] * width)), width - 1)
            conf_mark = " " * pos + "|"
        lines.append(
            f"[{b['bin_low']:.1f}-{b['bin_high']:.1f}] "
            f"{bar} {conf_mark} "
            f"acc={b['accuracy']:.2f} conf={b['avg_confidence']:.2f} n={n}")
    lines.append("```")
    lines.append("`#` = bin accuracy, `|` = bin mean confidence. "
                 "Aligned tip+mark = calibrated.")
    return "\n".join(lines)


def _methodology_block(report: Mapping[str, Any]) -> str:
    plat = report.get("platform", {})
    return "\n".join([
        "## Methodology & hardware",
        "",
        f"- HugrGate version: {report.get('hugrgate_version', 'unknown')}",
        f"- Dataset: {report.get('dataset', '?')} "
        f"(v{report.get('dataset_version', '?')}, "
        f"fingerprint `{report.get('dataset_fingerprint', '?')}`, "
        f"n={report.get('n_items', '?')})",
        f"- Generated at: {report.get('generated_at', '?')}",
        f"- OS: {plat.get('system', '?')} {plat.get('release', '')} "
        f"({plat.get('machine', '?')})",
        f"- Python: {plat.get('python', '?')}",
        f"- CPU: {plat.get('processor', 'unknown')}",
        "- Latency: per-decision wall time measured inside "
        "`HugrGate.decide` via `time.perf_counter` (includes backend "
        "inference, validation, policy gate and provenance append).",
        "- Throughput: decided items / total wall seconds for that backend.",
        "- Brier score: mean squared error of the full predicted "
        "distribution against the one-hot truth.",
        "- ECE: 10 equal-width confidence bins, "
        "sum |acc - conf| weighted by bin mass.",
        "- Accuracy: exact match of `result.value` against the expected "
        "label (set equality for multilabel specs).",
    ])


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a full markdown report from a benchmark JSON dict."""
    backends = report.get("backends", {})
    lines = [
        f"# HugrGate benchmark report — {report.get('dataset', '?')}",
        "",
        "## Summary",
        "",
        _metric_table(backends),
        "",
    ]
    for name, metrics in backends.items():
        lines += [
            f"## {name}",
            "",
            f"- Decided: {metrics['n_decided']}, abstained: "
            f"{metrics['n_abstained']} "
            f"({metrics['abstention_rate']:.1%}), "
            f"errors: {metrics['n_errors']}",
            f"- Accuracy: {_fmt(metrics['accuracy'])}",
            f"- Brier score: {_fmt(metrics['brier_score'])} "
            "(lower is better)",
            f"- ECE: {_fmt(metrics['ece'])} (lower is better)",
            f"- Latency: p50 {_fmt(metrics['latency_p50_ms'], 1)} ms, "
            f"p99 {_fmt(metrics['latency_p99_ms'], 1)} ms, "
            f"mean {_fmt(metrics['latency_mean_ms'], 1)} ms",
            f"- Throughput: {_fmt(metrics['throughput_per_s'], 1)} dec/s",
            f"- Calibration info: `{metrics.get('calibration', {})}`",
            "",
            "### Reliability diagram",
            "",
            ascii_reliability_diagram(metrics["reliability_bins"]),
            "",
        ]
    lines += ["", _methodology_block(report), ""]
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], path: str) -> str:
    """Render and write the markdown report; returns the path."""
    text = render_markdown(report)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
