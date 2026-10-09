"""Record the energy-model artifact. Slice 341.

The energy interface's honest core: this script does NOT measure
hardware.  It records

1. the coefficient table's provenance (what the defaults are and why
   they are estimates),
2. a determinism check (same inputs -> same outputs), and
3. a worked example comparing the default model against a zero-power
   baseline,

into ``benchmarks/observability_energy_341.json`` so operators can
see exactly what the numbers mean.

    python benchmarks/observability_energy_341.py
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.observability.energy import (
    DEFAULT_POWER_W,
    DefaultEnergyEstimator,
    EnergyMetrics,
)


def main() -> None:
    estimator = DefaultEnergyEstimator()
    # 1. determinism: identical inputs give identical outputs.
    first = [estimator.estimate_wh("gpu", 123.4) for _ in range(3)]
    assert len(set(first)) == 1, "estimator is not deterministic"
    # 2. worked example vs the zero-power baseline.
    example = {
        backend: {
            "latency_ms": 100.0,
            "estimated_wh": estimator.estimate_wh(backend, 100.0),
            "baseline_zero_wh": 0.0,
        }
        for backend in ("cpu", "gpu", "npu", "remote", "mystery-backend")
    }
    # 3. end-to-end through the metrics aggregator.
    metrics = EnergyMetrics(estimator=estimator)
    metrics.record("gpu", 100.0)
    metrics.record("cpu", 50.0, energy_wh=0.0005)  # metered override
    artifact = {
        "slice": 341,
        "recorded_at": time.time(),
        "host": platform.node(),
        "model": estimator.describe(),
        "coefficient_provenance": {
            name: ("nameplate-ish average for capacity planning; "
                   "NOT a meter reading")
            for name in DEFAULT_POWER_W
        },
        "determinism_check": {
            "inputs": {"backend": "gpu", "latency_ms": 123.4},
            "outputs_wh": first,
            "deterministic": True,
        },
        "worked_example_100ms": example,
        "aggregator_summary": metrics.summary(),
    }
    out = Path("benchmarks/observability_energy_341.json")
    out.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact["aggregator_summary"], indent=2))


if __name__ == "__main__":
    main()
