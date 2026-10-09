"""Public report generator — the lab's story in Markdown. Slice 374.

:func:`render_lab_markdown` assembles a public-facing evaluation
report from lab artifacts: the run record (dataset identity,
metric tables), head-to-head comparisons, CI gate outcomes,
regression findings, and the reproducibility manifest.  When a v1
bench JSON is supplied, its full rendering (via
:mod:`hugrgate.bench_report`, slice 47) is embedded as the
benchmark-detail section — reuse, not duplication.

Every section degrades gracefully: missing pieces render as
explicit "not evaluated" lines, never as silent gaps.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hugrgate.bench_report import render_markdown as _render_bench_markdown
from hugrgate.errors import EvalError
from hugrgate.evlab.api import RunRecord

__all__ = [
    "LabReport",
    "lab_report_from_run",
    "render_lab_markdown",
    "write_lab_report",
]

_PREFERRED_METRICS = (
    "accuracy",
    "brier_score",
    "ece",
    "abstention_rate",
    "latency_p50_ms",
    "latency_p99_ms",
    "throughput_per_s",
)


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LabReport:
    """Assembled inputs for one public lab report (slice 374)."""

    title: str
    generated_at: str = field(default_factory=_utcnow)
    run: RunRecord | None = None
    bench_json: Mapping[str, Any] | None = None
    comparisons: list[dict[str, Any]] = field(default_factory=list)
    gate_results: list[dict[str, Any]] = field(default_factory=list)
    regressions: list[dict[str, Any]] = field(default_factory=list)
    repro: Mapping[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "run": self.run.to_dict() if self.run else None,
            "bench_json": dict(self.bench_json)
            if self.bench_json else None,
            "comparisons": [dict(c) for c in self.comparisons],
            "gate_results": [dict(g) for g in self.gate_results],
            "regressions": [dict(r) for r in self.regressions],
            "repro": dict(self.repro) if self.repro else None,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LabReport:
        run = data.get("run")
        return cls(
            title=data["title"],
            generated_at=data.get("generated_at", _utcnow()),
            run=RunRecord.from_dict(run) if run else None,
            bench_json=(dict(data["bench_json"])
                        if data.get("bench_json") else None),
            comparisons=[dict(c)
                         for c in data.get("comparisons", [])],
            gate_results=[dict(g)
                          for g in data.get("gate_results", [])],
            regressions=[dict(r)
                         for r in data.get("regressions", [])],
            repro=dict(data["repro"]) if data.get("repro") else None,
            notes=list(data.get("notes", [])),
        )


def lab_report_from_run(
    record: RunRecord,
    title: str | None = None,
    comparisons: Sequence[Mapping[str, Any]] = (),
    gate_results: Sequence[Mapping[str, Any]] = (),
    regressions: Sequence[Mapping[str, Any]] = (),
    repro: Mapping[str, Any] | None = None,
    bench_json: Mapping[str, Any] | None = None,
    notes: Sequence[str] = (),
) -> LabReport:
    """Assemble a :class:`LabReport` around one run record."""
    if not isinstance(record, RunRecord):
        raise EvalError(
            f"lab_report_from_run needs a RunRecord, got "
            f"{type(record).__name__}")
    return LabReport(
        title=title or f"Evaluation report — {record.dataset_name}",
        run=record,
        bench_json=dict(bench_json) if bench_json else None,
        comparisons=[dict(c) for c in comparisons],
        gate_results=[dict(g) for g in gate_results],
        regressions=[dict(r) for r in regressions],
        repro=dict(repro) if repro else None,
        notes=list(notes),
    )


def _metric_columns(
    backends: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    preferred = [m for m in _PREFERRED_METRICS
                 if any(isinstance(b.get(m), (int, float))
                        and not isinstance(b.get(m), bool)
                        for b in backends.values())]
    rest = sorted(
        {k for b in backends.values() for k, v in b.items()
         if k not in preferred and isinstance(v, (int, float))
         and not isinstance(v, bool)})
    return preferred + rest


def _run_section(record: RunRecord) -> list[str]:
    lines = [
        "## Run",
        "",
        f"- Dataset: `{record.dataset_name}` v{record.dataset_version}",
        f"- Fingerprint: `{record.dataset_fingerprint}`",
        f"- Items: {record.n_items}, seed: {record.seed}",
        f"- Backends: {', '.join(sorted(record.backends))}",
        f"- HugrGate: {record.hugrgate_version}, "
        f"Python: {record.python_version}",
        f"- Git SHA: {record.git_sha or 'unknown'}",
        f"- Ran: {record.finished_at} "
        f"({record.elapsed_s:.1f}s, privacy class "
        f"`{record.privacy_class}`)",
        "",
        "### Metrics",
        "",
    ]
    columns = _metric_columns(record.backends)
    if not columns:
        lines += ["No numeric metrics recorded.", ""]
        return lines
    header = "| backend | " + " | ".join(columns) + " |"
    lines += [header, "|" + "|".join(["---"] * (len(columns) + 1)) + "|"]
    for backend in sorted(record.backends):
        metrics = record.backends[backend]
        row = " | ".join(_fmt(metrics.get(c)) for c in columns)
        lines.append(f"| {backend} | {row} |")
    lines.append("")
    return lines


def _comparisons_section(
    comparisons: Sequence[Mapping[str, Any]]
) -> list[str]:
    lines = ["## Head-to-head comparisons", ""]
    if not comparisons:
        return [*lines, "No comparisons evaluated.", ""]
    for comp in comparisons:
        verdict = comp.get("verdict", "?")
        lines.append(
            f"- `{comp.get('backend_a')}` vs `{comp.get('backend_b')}` "
            f"on `{comp.get('metric')}`: **{verdict}** "
            f"(a={_fmt(comp.get('estimate_a'))}, "
            f"b={_fmt(comp.get('estimate_b'))}, "
            f"diff CI [{_fmt(comp.get('diff_ci_low'))}, "
            f"{_fmt(comp.get('diff_ci_high'))}], "
            f"p={_fmt(comp.get('p_value'))}, "
            f"wins {comp.get('wins_a')}/{comp.get('wins_b')}/"
            f"{comp.get('ties')} a/b/tie)")
    return [*lines, ""]


def _gates_section(gate_results: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = ["## Quality gates", ""]
    if not gate_results:
        return [*lines, "No gates evaluated.", ""]
    lines += ["| gate | backend | check | actual | result |",
              "|---|---|---|---|---|"]
    for res in gate_results:
        mark = "PASS" if res.get("passed") else "FAIL"
        lines.append(
            f"| {res.get('gate')} | {res.get('backend')} | "
            f"`{res.get('metric')}` {res.get('op')} "
            f"{_fmt(res.get('threshold'))} | "
            f"{_fmt(res.get('actual'))} | **{mark}** |")
    return [*lines, ""]


def _regressions_section(
    regressions: Sequence[Mapping[str, Any]]
) -> list[str]:
    lines = ["## Regressions", ""]
    if not regressions:
        return [*lines, "No regressions detected.", ""]
    for reg in regressions:
        lines.append(
            f"- `{reg.get('backend')}` / `{reg.get('metric')}` on "
            f"`{reg.get('dataset')}`: {_fmt(reg.get('current'))} vs "
            f"baseline {_fmt(reg.get('baseline'))} "
            f"(drop {_fmt(reg.get('drop'))}; "
            f"{reg.get('baseline_run_id')} -> "
            f"{reg.get('current_run_id')})")
    return [*lines, ""]


def _repro_section(repro: Mapping[str, Any] | None) -> list[str]:
    lines = ["## Reproducibility", ""]
    if not repro:
        return [*lines, "No reproducibility manifest attached.", ""]
    return [*lines,
        f"- Dataset: `{repro.get('dataset_name')}` "
        f"v{repro.get('dataset_version')} "
        f"(`{repro.get('dataset_fingerprint')}`)",
        f"- Backends: {', '.join(repro.get('backends', []))}, "
        f"seed: {repro.get('seed')}",
        f"- HugrGate {repro.get('hugrgate_version')}, "
        f"Python {repro.get('python_version')}",
        f"- Git SHA: {repro.get('git_sha') or 'unknown'}",
        f"- Command: `{repro.get('command') or 'not recorded'}`",
        "",
    ]


def render_lab_markdown(report: LabReport) -> str:
    """Render a :class:`LabReport` to Markdown."""
    if not isinstance(report, LabReport):
        raise EvalError(
            f"render_lab_markdown needs a LabReport, got "
            f"{type(report).__name__}")
    lines = [f"# {report.title}", "",
             f"_Generated {report.generated_at} by HugrGate "
             "Evaluation Laboratory._", ""]
    if report.run is not None:
        lines += _run_section(report.run)
    else:
        lines += ["## Run", "", "No run record attached.", ""]
    lines += _comparisons_section(report.comparisons)
    lines += _gates_section(report.gate_results)
    lines += _regressions_section(report.regressions)
    lines += _repro_section(report.repro)
    if report.bench_json is not None:
        lines += ["## Benchmark detail", "",
                  _render_bench_markdown(report.bench_json), ""]
    if report.notes:
        lines += ["## Notes", ""]
        lines += [f"- {note}" for note in report.notes] + [""]
    return "\n".join(lines)


def write_lab_report(report: LabReport, path: str | Path) -> str:
    """Render and write the report; returns the path as a string."""
    text = render_lab_markdown(report)
    target = Path(path)
    if target.exists():
        raise EvalError(
            f"report path {str(target)!r} already exists; refusing "
            "to overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)
