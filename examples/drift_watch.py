"""Drift watch — calibration drift detection in action (Slice 48).

Fits a DriftMonitor on calibration-time confidences (keyword backend),
then observes a shifted live window (uniform backend — flat, unsure
predictions) and prints the PSI plus the recalibration advisory.

Run:  venv/bin/python examples/drift_watch.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate import DecisionSpec  # noqa: E402
from hugrgate.drift import DriftMonitor, recalibration_advisory  # noqa: E402
from hugrgate.server import build_gate  # noqa: E402


def confidences(gate, spec, items, backend):
    out = []
    for item in items:
        out.append(gate.decide(item["state"], spec,
                               backend_name=backend).probability)
    return out


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    with open(root / "benchmarks" / "triage_500.json",
              encoding="utf-8") as f:
        dataset = json.load(f)
    spec = DecisionSpec.from_dict(dataset["spec"])
    gate = build_gate()

    monitor = DriftMonitor(alert_threshold=0.25)
    reference = confidences(gate, spec, dataset["items"][:200], "keyword")
    monitor.fit_reference(reference)
    print(f"fitted reference on {len(reference)} calibration confidences "
          f"(mean={sum(reference) / len(reference):.3f})")

    # Healthy live traffic: same backend, same distribution.
    healthy = confidences(gate, spec, dataset["items"][200:300], "keyword")
    report = monitor.observe(healthy)
    print(f"\nhealthy window: PSI={report.psi:.4f} "
          f"severity={report.severity} alert={report.alert}")

    # Shifted live traffic: a degraded backend took over.
    shifted = confidences(gate, spec, dataset["items"][200:300], "uniform")
    report = monitor.observe(shifted)
    print(f"shifted window: PSI={report.psi:.4f} "
          f"severity={report.severity} alert={report.alert}")

    advisory = recalibration_advisory(report)
    print(f"\nadvisory: {advisory['message']}")
    for step in advisory.get("recommended_steps", []):
        print(f"  - {step}")


if __name__ == "__main__":
    main()
