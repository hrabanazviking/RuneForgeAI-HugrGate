"""Benchmark run — harness over an original dataset (Slice 47).

Runs the keyword and uniform baselines over benchmarks/triage_500.json,
prints the metric table, and writes a full markdown report (tables +
ASCII reliability diagrams + methodology) to /tmp.

Run:  venv/bin/python examples/benchmark_run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.bench import run_benchmark  # noqa: E402
from hugrgate.bench_report import write_report  # noqa: E402
from hugrgate.server import build_gate  # noqa: E402

REPORT_MD = "/tmp/hugrgate_bench_report.md"


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    with open(root / "benchmarks" / "triage_500.json",
              encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Benchmarking {dataset['name']} "
          f"({len(dataset['items'])} items) ...")
    report = run_benchmark(dataset, build_gate(),
                           backends=["keyword", "uniform"])

    print(f"\n{'backend':<10} {'acc':>6} {'brier':>6} {'ece':>6} "
          f"{'p50 ms':>8} {'p99 ms':>8} {'dec/s':>8}")
    for name, m in report["backends"].items():
        acc = f"{m['accuracy']:.3f}" if m["accuracy"] is not None else "n/a"
        print(f"{name:<10} {acc:>6} {m['brier_score']:>6.3f} "
              f"{m['ece']:>6.3f} {m['latency_p50_ms']:>8.1f} "
              f"{m['latency_p99_ms']:>8.1f} {m['throughput_per_s']:>8.1f}")

    write_report(report, REPORT_MD)
    print(f"\nFull markdown report written to {REPORT_MD}")
    print("Note the keyword backend's ECE: high accuracy, overconfident "
          "probabilities — exactly what calibration (docs/calibration.md) "
          "is for.")


if __name__ == "__main__":
    main()
